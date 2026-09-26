(function () {
  "use strict";

  const NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
  const MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const brokerName = value => value === "toss" ? "Toss Securities" : "KIS";
  const marketName = value => value === "us" ? "US" : "KR";
  const numeric = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const excelSerial = iso => {
    const time = Date.parse(`${String(iso).slice(0, 10)}T00:00:00Z`);
    return Number.isFinite(time) ? time / 86400000 + 25569 : null;
  };

  function cells(document) {
    return new Map([...document.getElementsByTagNameNS(NS, "c")].map(cell => [cell.getAttribute("r"), cell]));
  }

  function clearCell(cell) {
    while (cell.firstChild) cell.removeChild(cell.firstChild);
    cell.removeAttribute("t");
  }

  function setCell(document, map, ref, value, type = "number") {
    const cell = map.get(ref);
    if (!cell) throw new Error(`엑셀 양식의 ${ref} 셀을 찾지 못했습니다.`);
    clearCell(cell);
    if (value == null || value === "") return;
    const node = document.createElementNS(NS, "x:v");
    node.textContent = String(value);
    cell.setAttribute("t", type === "string" ? "str" : "n");
    cell.appendChild(node);
  }

  function clearBody(map, maxRow, columns) {
    const allowed = new Set(columns);
    for (const [ref, cell] of map) {
      const match = /^([A-Z]+)(\d+)$/.exec(ref);
      if (match && allowed.has(match[1]) && Number(match[2]) >= 2 && Number(match[2]) <= maxRow) clearCell(cell);
    }
  }

  function parseXml(text) {
    const document = new DOMParser().parseFromString(text, "application/xml");
    if (document.querySelector("parsererror")) throw new Error("엑셀 양식을 읽지 못했습니다.");
    return document;
  }

  function serialize(document) {
    return new XMLSerializer().serializeToString(document);
  }

  function snapshotTotals(snapshot) {
    if (snapshot?.totals?.kr && snapshot?.totals?.us) return snapshot.totals;
    const totals = { kr: { evaluation_amount: 0 }, us: { evaluation_amount: 0 } };
    for (const item of snapshot?.positions || []) totals[item.market === "us" ? "us" : "kr"].evaluation_amount += numeric(item.evaluation_amount) || 0;
    return totals;
  }

  function downloadBlob(blob, fileName) {
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = fileName; document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function download(portfolio) {
    if (!window.JSZip) throw new Error("엑셀 생성 모듈을 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요.");
    const history = [...(portfolio?.history || [])].sort((a, b) => String(a.snapshot_date).localeCompare(String(b.snapshot_date))).slice(-366);
    if (!history.length) throw new Error("다운로드할 일별 계좌 기록이 아직 없습니다.");
    const response = await fetch("assets/stock-portfolio-history-template.xlsx", { cache: "no-store" });
    if (!response.ok) throw new Error("엑셀 양식을 불러오지 못했습니다.");
    const zip = await window.JSZip.loadAsync(await response.arrayBuffer());

    const summaryDoc = parseXml(await zip.file("xl/worksheets/sheet1.xml").async("string"));
    const totalsDoc = parseXml(await zip.file("xl/worksheets/sheet2.xml").async("string"));
    const recordsDoc = parseXml(await zip.file("xl/worksheets/sheet3.xml").async("string"));
    const summaryCells = cells(summaryDoc), totalCells = cells(totalsDoc), recordCells = cells(recordsDoc);
    clearBody(totalCells, 367, ["A", "B", "C", "D"]);
    clearBody(recordCells, 5001, ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"]);

    const totalRows = history.map(snapshot => {
      const totals = snapshotTotals(snapshot);
      return [snapshot.snapshot_date, numeric(totals.kr?.evaluation_amount) || 0, numeric(totals.us?.evaluation_amount) || 0, (snapshot.positions || []).length];
    });
    totalRows.forEach((row, index) => {
      const excelRow = index + 2;
      setCell(totalsDoc, totalCells, `A${excelRow}`, row[0], "string");
      setCell(totalsDoc, totalCells, `B${excelRow}`, row[1]);
      setCell(totalsDoc, totalCells, `C${excelRow}`, row[2]);
      setCell(totalsDoc, totalCells, `D${excelRow}`, row[3]);
    });

    const detailRows = history.flatMap(snapshot => (snapshot.positions || []).map(item => [
      excelSerial(snapshot.snapshot_date), brokerName(item.broker), marketName(item.market), item.symbol, item.name,
      numeric(item.quantity), numeric(item.average_price), numeric(item.current_price), numeric(item.evaluation_amount),
      numeric(item.profit_loss), numeric(item.profit_rate) == null ? null : numeric(item.profit_rate) / 100,
      numeric(item.daily_change_rate) == null ? null : numeric(item.daily_change_rate) / 100, item.currency,
    ])).slice(-5000);
    const letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"];
    const stringColumns = new Set([1, 2, 3, 4, 12]);
    detailRows.forEach((row, index) => row.forEach((value, column) => setCell(recordsDoc, recordCells, `${letters[column]}${index + 2}`, value, stringColumns.has(column) ? "string" : "number")));

    const latest = history[history.length - 1], latestTotals = snapshotTotals(latest);
    setCell(summaryDoc, summaryCells, "B5", latest.snapshot_date, "string");
    setCell(summaryDoc, summaryCells, "B7", numeric(latestTotals.kr?.evaluation_amount) || 0);
    setCell(summaryDoc, summaryCells, "E7", numeric(latestTotals.us?.evaluation_amount) || 0);
    setCell(summaryDoc, summaryCells, "H7", (latest.positions || []).length);

    zip.file("xl/worksheets/sheet1.xml", serialize(summaryDoc));
    zip.file("xl/worksheets/sheet2.xml", serialize(totalsDoc));
    zip.file("xl/worksheets/sheet3.xml", serialize(recordsDoc));
    const workbookXml = await zip.file("xl/workbook.xml").async("string");
    zip.file("xl/workbook.xml", workbookXml.includes("<x:calcPr") ? workbookXml : workbookXml.replace("</x:workbook>", '<x:calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1" /></x:workbook>'));
    const blob = await zip.generateAsync({ type: "blob", mimeType: MIME, compression: "DEFLATE" });
    downloadBlob(blob, `stock-portfolio-history-${latest.snapshot_date}.xlsx`);
    return { days: history.length, records: detailRows.length, truncated: detailRows.length === 5000 };
  }

  window.PortfolioExcel = { download };
})();
