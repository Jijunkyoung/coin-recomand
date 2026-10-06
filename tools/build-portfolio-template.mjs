import fs from 'node:fs/promises';
import {SpreadsheetFile, Workbook} from '@oai/artifact-tool';
// Editable native XLSX template. Runtime exporters replace sample inputs and resize bindings.
const out=process.argv[2] || 'stock-portfolio-history-template.xlsx';
const w=Workbook.create();
const summary=w.worksheets.add('요약'), totals=w.worksheets.add('일별총액'), records=w.worksheets.add('종목별기록'), current=w.worksheets.add('최근보유종목');
const font='NanumGothic', blue='#152B4F', money='#,##0;(#,##0);"-"';
function base(s,r){s.showGridLines=false;s.getRange(r).format.font={name:font,size:10,color:'#152B4F'};s.getRange(r).format.rowHeight=24;s.getRange(r).format.verticalAlignment='center';}
function table(s,ref,name){s.tables.add(ref,true,name);s.getRange(ref.split(':')[0]+':'+ref.split(':')[1].replace(/\d+$/,'1')).format={fill:blue,font:{name:font,size:10,bold:true,color:'#FFFFFF'},rowHeight:30,horizontalAlignment:'center'};s.freezePanes.freezeRows(1);}
base(summary,'A1:N48');summary.getRange('A1:N48').format.columnWidth=12;summary.getRange('A2').values=[['일별 보유자산']];summary.getRange('A2').format.font={name:font,size:16,bold:true,color:blue};
summary.getRange('A4:N4').format.borders={bottom:{style:'thin',color:'#8BA1BD'}};
summary.getRange('A5').values=[['기준일']];summary.getRange('B5').formulas=[["='일별총액'!A8"]];summary.getRange('B5').setNumberFormat('yyyy-mm-dd');
summary.getRange('A7').values=[['총 보유자산 (원)']];summary.getRange('D7').values=[['국내주식 (원)']];summary.getRange('G7').values=[['미국주식 (USD)']];summary.getRange('J7').values=[['업비트 자산 (원)']];
for(const [ref,col] of [['A8','F'],['D8','B'],['G8','C'],['J8','D']]){summary.getRange(ref).formulas=[[`='일별총액'!${col}8`]];summary.getRange(ref).setNumberFormat(money);summary.getRange(ref).format.font={name:font,size:14,bold:true,color:blue};}
summary.getRange('A10').values=[['연결계좌의 주식·업비트 원화·코인 기준. 주식 예수금과 다른 금융자산은 미포함.']];
summary.getRange('A11').values=[['미국주식은 날짜별 환율로 원화 환산. 조회자료·환율 누락 시 총액은 n.a.로 표시.']];
summary.getRange('A10:N11').format.font={name:font,size:10,italic:true,color:'#52677E'};
base(totals,'A1:K8');totals.getRange('A1:K8').format.columnWidth=20;
totals.getRange('A1:K1').values=[['날짜','국내주식 (KRW)','미국주식 (USD)','업비트 자산 (KRW)','USD/KRW 환율','총 보유자산 (KRW)','보유종목 수','자료 상태','환율 기준일','조회·환율 안내','차트 날짜']];
const sample=Array.from({length:7},(_,i)=>[new Date(Date.UTC(2026,8,20+i)),6100000+i*125000,2500+i*73.3,1500000+i*20000,1370+i,null,4,'정상',new Date(Date.UTC(2026,8,18+i)),'예시 데이터',`2026-09-${20+i}`]);
totals.getRange('A2:K8').values=sample;
totals.getRange('F2').formulas=[['=IF(H2="자료누락","n.a.",IF(C2=0,SUM(B2,D2),IF(ISNUMBER(E2),SUM(B2,D2,C2*E2),"n.a.")))']];totals.getRange('F2:F8').fillDown();
totals.getRange('A2:A8').setNumberFormat('yyyy-mm-dd');totals.getRange('I2:I8').setNumberFormat('yyyy-mm-dd');totals.getRange('B2:F8').setNumberFormat(money);totals.getRange('C2:C8').setNumberFormat('#,##0.00');totals.getRange('E2:E8').setNumberFormat('0.0000');totals.getRange('G2:G8').setNumberFormat('0');totals.getRange('J1:J8').format.columnWidth=60;table(totals,'A1:K8','DailyAssets');
const headers=['날짜','증권사·거래소','시장','종목코드','종목명','수량','평균매수가','현재가','평가금액','평가손익','수익률','일간 등락률','통화','USD/KRW 환율','원화 환산금액','자료 조회시각'];
const samples=[[46291,'한국투자증권','국내','005930','삼성전자',50,62000,72000,3600000,500000,.1613,.0141,'KRW',1376,null,'2026-09-26T07:10:00+09:00'],[46291,'토스증권','국내','000660','SK하이닉스',10,290000,325000,3250000,350000,.1207,-.006,'KRW',1376,null,'2026-09-26T07:10:00+09:00'],[46291,'토스증권','미국','AAPL','Apple',10,260,294,2940,340,.1308,.008,'USD',1376,null,'2026-09-26T07:10:00+09:00'],[46291,'업비트','코인','BTC','BTC',.01,130000000,140000000,1400000,100000,.0769,.01,'KRW',1376,null,'2026-09-26T07:10:00+09:00']];
for(const s of [records,current]){base(s,'A1:P5');s.getRange('A1:P5').format.columnWidth=18;s.getRange('A1:P1').values=[headers];s.getRange('A2:P5').values=samples;s.getRange('E1:E5').format.columnWidth=24;s.getRange('P1:P5').format.columnWidth=30;s.getRange('A2:A5').setNumberFormat('yyyy-mm-dd');s.getRange('F2:F5').setNumberFormat('0.########');s.getRange('G2:J5').setNumberFormat(money);s.getRange('K2:L5').setNumberFormat('0.0%');s.getRange('N2:N5').setNumberFormat('0.0000');s.getRange('O2:O5').setNumberFormat(money);s.getRange('O2').formulas=[['=IF(M2="KRW",I2,IF(ISNUMBER(N2),I2*N2,"n.a."))']];s.getRange('O2:O5').fillDown();table(s,'A1:P5',s===records?'AssetRecords':'CurrentAssets');}
for(const s of [records,current]){s.getRange('D2:D5').setNumberFormat('@');}
const chart1=summary.charts.add('line',[totals.getRange('K1:K8'),totals.getRange('F1:F8')]);chart1.title='총 보유자산 추이 (KRW)';chart1.setPosition('A14','N29');
const chart2=summary.charts.add('bar',[current.getRange('E1:E5'),current.getRange('O1:O5')]);chart2.title='최근 보유종목 금액 (KRW, 상위 10개)';chart2.setPosition('A31','N47');
for(const c of [chart1,chart2]){c.hasLegend=false;c.titleTextStyle.typeface=font;c.titleTextStyle.fontSize=13;c.xAxis={axisType:'textAxis',textStyle:{typeface:font,fontSize:10}};c.yAxis={numberFormatCode:'#,##0,,"백만"',numberFormatSourceLinked:false,textStyle:{typeface:font,fontSize:10}};}
chart1.series.items[0].line={fill:'#2C65C8',style:'solid',width:2};chart2.series.items[0].fill='#2C65C8';
w.recalculate();
console.log((await w.inspect({kind:'table',range:'일별총액!A1:I8',include:'values,formulas',tableMaxRows:8,tableMaxCols:9,maxChars:1500})).ndjson);
console.log((await w.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},summary:'template error scan'})).ndjson);
for(const [s,r] of [[summary,'A1:N48'],[totals,'A1:I8'],[records,'A1:J5'],[current,'A1:J5']]){const b=await w.render({sheetName:s.name,range:r,scale:1,format:'png'});await fs.writeFile(`/tmp/daily-asset-excel-20261006/${s.name}.png`,new Uint8Array(await b.arrayBuffer()));}
await (await SpreadsheetFile.exportXlsx(w)).save(out);
// A changed exchange rate must update both converted holdings and the headline total.
totals.getRange('E8').values=[[1500]];if(totals.getRange('F8').values[0][0]!==6850000+1620000+2939.8*1500)throw new Error('FX recalculation failed');
console.log('Template and native charts exported; FX recalculation verified.');
