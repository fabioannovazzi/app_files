import fs from 'node:fs/promises';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root = process.argv[2];
if (!root || !process.argv[3]) throw Error('Usage: build_concordato_inputs.mjs <course-materials-dir> <preview-dir>');
const output = `${root}/inputs/concordato`;
const previews = process.argv[3];
await fs.mkdir(output, {recursive:true});
await fs.mkdir(previews, {recursive:true});
const texts=JSON.parse(await fs.readFile(`${root}/concordato_sources.json`,'utf8'));
for (const [lang,t] of Object.entries(texts)) {
 for (const phase of ['demo','practice']) {
  const wb=Workbook.create();
  const sheets=t.tabs.map(n=>wb.worksheets.add(n));
  for(const s of sheets){s.showGridLines=false;s.getRange('A1:F18').format.font={name:'Arial',size:11,color:'#243441'};s.getRange('A1:F18').format.verticalAlignment='center';}
  const [c,r,p]=sheets;
  c.getRange('A2').values=[[t.title]];c.getRange('A2').format.font={name:'Arial',size:16,bold:true};
  c.getRange('A4').values=[[t.fiction]];c.getRange('A4').format.font.italic=true;
  c.getRange('A6:B13').values=t.fields.map((label,i)=>[label,phase==='practice'&&i===5?t.notes[7]:t.notes[i]]);
  c.getRange('A13:B13').clear({applyTo:'contents'});
  c.getRange('A1:A13').format.columnWidthPx=220;c.getRange('B1:B13').format.columnWidthPx=820;
  c.getRange('A6:B13').format.wrapText=true;c.getRange('A6:A13').format.font.bold=true;
  c.getRange('A6:B13').format.rowHeightPx=70;c.getRange('A4:B4').format.rowHeightPx=35;
  c.getRange('A6:B13').format.verticalAlignment='top';
  r.getRange('A2').values=[[t.tabs[1]]];r.getRange('A2').format.font={name:'Arial',size:16,bold:true};
  r.getRange('A4').values=[[t.fiction]];r.getRange('A4').format.font.italic=true;
  r.getRange('A6:D9').values=[t.creditorHeaders,['Alba Componenti',100000,65000,45000],['Borea Materiali',60000,39000,27000],['Cima Trasporti',40000,26000,18000]];
  r.getRange('A1:D10').format.columnWidthPx=265;r.getRange('A6:D9').format.rowHeightPx=40;
  r.getRange('A6:D6').format={fill:'#314958',font:{color:'#FFFFFF',bold:true},horizontalAlignment:'center',wrapText:true};
  r.getRange('B7:D9').setNumberFormat('#,##0;(#,##0);"-"');r.getRange('B7:D9').format.font.color='#0000FF';
  p.getRange('A2').values=[[t.planTitle]];p.getRange('A2').format.font={name:'Arial',size:16,bold:true};
  p.getRange('A14').values=[[t.planNote]];p.getRange('A14').format.font.italic=true;
  p.getRange('A14').format.wrapText=true;p.getRange('A14:B14').format.rowHeightPx=110;
  p.getRange('A6:B12').values=t.metrics.map((label,i)=>[label,[300000,200000,phase==='demo'?50000:30000,20000,130000,0,null][i]]);
  p.getRange('B12').formulas=[['=B11+B6-B7+B8-B9-B10']];
  p.getRange('A1:A12').format.columnWidthPx=430;p.getRange('B1:B12').format.columnWidthPx=190;
  p.getRange('A6:B12').format.rowHeightPx=38;p.getRange('B6:B12').setNumberFormat('#,##0;(#,##0);"-"');
  p.getRange('B6:B11').format.font.color='#0000FF';p.getRange('A12:B12').format.font.bold=true;
  p.getRange('A12:B12').format.borders={top:{style:'thin',color:'#314958'}};
  // Source statements remain plain inputs. The workflow authors its own review.
  wb.recalculate();
  const expected=phase==='demo'?0:-20000;
  if(p.getRange('B12').values[0][0]!==expected) throw Error(`Closing cash mismatch: ${lang}/${phase}`);
  const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:10},maxChars:1000});
  console.log(lang,phase,errors.ndjson);
  for(let i=0;i<sheets.length;i++){
   const range=i===0?'A1:B13':i===1?'A1:D10':'A1:B15';
   const blob=await wb.render({sheetName:t.tabs[i],range,scale:1,format:'png'});
   await fs.writeFile(`${previews}/${lang}-${phase}-${i}.png`,new Uint8Array(await blob.arrayBuffer()));
  }
  const file=await SpreadsheetFile.exportXlsx(wb);
  await file.save(`${output}/${phase}-${lang}.xlsx`);
 }
}

