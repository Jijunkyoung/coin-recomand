(function () {
  "use strict";
  const NS="http://schemas.openxmlformats.org/spreadsheetml/2006/main",CNS="http://schemas.openxmlformats.org/drawingml/2006/chart";
  const MIME="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  const parse=text=>{const d=new DOMParser().parseFromString(text,"application/xml");if(d.querySelector("parsererror"))throw new Error("엑셀 양식을 읽지 못했습니다.");return d;};
  const xml=d=>new XMLSerializer().serializeToString(d);
  function writeCell(d,c,value){
    while(c.firstChild)c.removeChild(c.firstChild);c.removeAttribute("t");
    if(value&&typeof value==="object"){const f=d.createElementNS(NS,"x:f");f.textContent=value.formula;c.appendChild(f);value=value.value;}
    if(value==null||value==="")return;
    const v=d.createElementNS(NS,"x:v");v.textContent=String(value);c.setAttribute("t",typeof value==="number"?"n":"str");c.appendChild(v);
  }
  function fillRows(d,rows,columns){
    const body=d.getElementsByTagNameNS(NS,"sheetData")[0],old=[...body.getElementsByTagNameNS(NS,"row")],sample=old.find(r=>r.getAttribute("r")==="2");
    const styles=new Map([...sample.children].map(c=>[c.getAttribute("r").replace(/\d+$/,""),c.getAttribute("s")]));
    for(const r of old)if(Number(r.getAttribute("r"))>=2)r.remove();
    rows.forEach((values,i)=>{const r=d.createElementNS(NS,"x:row");r.setAttribute("r",i+2);if(sample.hasAttribute("ht")){r.setAttribute("ht",sample.getAttribute("ht"));r.setAttribute("customHeight","1");}values.forEach((v,j)=>{const col=String.fromCharCode(65+j),c=d.createElementNS(NS,"x:c");c.setAttribute("r",`${col}${i+2}`);if(styles.get(col)!=null)c.setAttribute("s",styles.get(col));writeCell(d,c,v);r.appendChild(c);});body.appendChild(r);});
    const dimension=d.getElementsByTagNameNS(NS,"dimension")[0];if(dimension)dimension.setAttribute("ref",`A1:${String.fromCharCode(64+columns)}${Math.max(2,rows.length+1)}`);
  }
  function chartCache(d,report){
    for(const [role,ref,data,kind] of [["cat",report.category,report.labels,"str"],["val",report.values,report.points,"num"]]){
      const parent=d.getElementsByTagNameNS(CNS,role)[0];while(parent.firstChild)parent.removeChild(parent.firstChild);
      const r=d.createElementNS(CNS,`c:${kind}Ref`),f=d.createElementNS(CNS,"c:f"),cache=d.createElementNS(CNS,`c:${kind}Cache`),count=d.createElementNS(CNS,"c:ptCount");f.textContent=ref;count.setAttribute("val",data.length);cache.appendChild(count);
      data.forEach((value,i)=>{if(value==null)return;const pt=d.createElementNS(CNS,"c:pt"),v=d.createElementNS(CNS,"c:v");pt.setAttribute("idx",i);v.textContent=String(value);pt.appendChild(v);cache.appendChild(pt);});r.appendChild(f);r.appendChild(cache);parent.appendChild(r);
    }
    if(d.getElementsByTagNameNS(CNS,"lineChart").length){
      const series=d.getElementsByTagNameNS(CNS,"ser")[0];let marker=series.getElementsByTagNameNS(CNS,"marker")[0];
      if(!marker){marker=d.createElementNS(CNS,"c:marker");series.insertBefore(marker,series.getElementsByTagNameNS(CNS,"cat")[0]);}
      while(marker.firstChild)marker.removeChild(marker.firstChild);
      const symbol=d.createElementNS(CNS,"c:symbol");symbol.setAttribute("val","circle");marker.appendChild(symbol);
      const size=d.createElementNS(CNS,"c:size");size.setAttribute("val","4");marker.appendChild(size);
      const axis=d.getElementsByTagNameNS(CNS,"catAx")[0];let skip=axis.getElementsByTagNameNS(CNS,"tickLblSkip")[0];
      if(!skip){skip=d.createElementNS(CNS,"c:tickLblSkip");axis.appendChild(skip);}skip.setAttribute("val",Math.max(1,Math.ceil(report.labels.length/8)));
    }
  }
  async function createBlob(portfolio){
    if(!window.JSZip)throw new Error("엑셀 생성 모듈을 불러오지 못했습니다. 새로고침 후 다시 시도해 주세요.");
    const {createReport}=await import("./portfolio-report.js?v=20261006-2"),report=createReport(portfolio);
    const response=await fetch("assets/stock-portfolio-history-template.xlsx?v=20261006-2",{cache:"no-store"});if(!response.ok)throw new Error("엑셀 양식을 불러오지 못했습니다.");
    const zip=await window.JSZip.loadAsync(await response.arrayBuffer());
    const summary=parse(await zip.file("xl/worksheets/sheet1.xml").async("string"));
    for(const item of report.summary){const cell=[...summary.getElementsByTagNameNS(NS,"c")].find(c=>c.getAttribute("r")===item.ref);if(!cell)throw new Error("엑셀 요약 양식이 올바르지 않습니다.");writeCell(summary,cell,item);}
    zip.file("xl/worksheets/sheet1.xml",xml(summary));
    for(const sheet of report.sheets){const d=parse(await zip.file(sheet.path).async("string"));fillRows(d,sheet.rows,sheet.columns);zip.file(sheet.path,xml(d));}
    for(const path of Object.keys(zip.files).filter(p=>/^xl\/tables\/.*\.xml$/.test(p))){const d=parse(await zip.file(path).async("string")),table=d.documentElement,sheet=report.sheets.find(s=>s.table===table.getAttribute("name"));if(!sheet)continue;const ref=`A1:${String.fromCharCode(64+sheet.columns)}${Math.max(2,sheet.rows.length+1)}`;table.setAttribute("ref",ref);for(const f of d.getElementsByTagNameNS(NS,"autoFilter"))f.setAttribute("ref",ref);zip.file(path,xml(d));}
    for(const chart of report.charts){const d=parse(await zip.file(chart.path).async("string"));chartCache(d,chart);zip.file(chart.path,xml(d));}
    const wb=parse(await zip.file("xl/workbook.xml").async("string"));let calc=wb.getElementsByTagNameNS(NS,"calcPr")[0];if(!calc){calc=wb.createElementNS(NS,"x:calcPr");wb.documentElement.appendChild(calc);}calc.setAttribute("calcMode","auto");calc.setAttribute("fullCalcOnLoad","1");calc.setAttribute("forceFullCalc","1");zip.file("xl/workbook.xml",xml(wb));
    return {blob:await zip.generateAsync({type:"blob",mimeType:MIME,compression:"DEFLATE"}),report};
  }
  async function download(portfolio){
    // Download always reads the complete owner history, including after a page reload.
    if(window.CoinAuth?.user&&window.CoinAuth.assetExport)portfolio=await window.CoinAuth.assetExport();
    const {blob,report}=await createBlob(portfolio),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=`portfolio-history-${report.date}.xlsx`;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);return {days:report.days,records:report.records};
  }
  window.PortfolioExcel={download,createBlob};
})();
