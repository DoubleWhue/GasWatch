(function(){
  const file=document.getElementById('pdf_file');
  if(file)file.addEventListener('change',()=>{const b=document.querySelector('.drop-area b'); if(b&&file.files.length)b.textContent=file.files[0].name;});
})();
function escapeHTML(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function drawTrendChart(){
  const el=document.getElementById('trend-chart');if(!el)return;
  const labels=JSON.parse(el.dataset.labels||'[]'),low=JSON.parse(el.dataset.low||'[]'),high=JSON.parse(el.dataset.high||'[]');
  if(!labels.length)return;
  const width=900,height=320,left=70,right=25,top=22,bottom=45;
  let lo=Math.min(...low,...high),hi=Math.max(...low,...high);if(lo===hi){lo-=1;hi+=1;}
  const span=hi-lo;lo-=span*.08;hi+=span*.08;
  const x=i=>left+(labels.length===1? .5 : i/(labels.length-1))*(width-left-right);
  const y=v=>height-bottom-(v-lo)/(hi-lo)*(height-top-bottom);
  const path=a=>a.map((v,i)=>(i?'L':'M')+x(i).toFixed(2)+','+y(v).toFixed(2)).join(' ');
  const grid=[0,1,2,3,4].map(i=>{const v=lo+(hi-lo)*(i/4),py=y(v);return `<line x1="${left}" y1="${py}" x2="${width-right}" y2="${py}" stroke="#e5eaf2"/><text x="${left-10}" y="${py+4}" text-anchor="end" fill="#738399" font-size="12">₱${v.toFixed(1)}</text>`;}).join('');
  const lbl=labels.map((s,i)=>{if(labels.length>8&&i%Math.ceil(labels.length/8)!==0)return '';return `<text x="${x(i)}" y="${height-12}" text-anchor="middle" fill="#718095" font-size="12">${escapeHTML(s.slice(5))}</text>`;}).join('');
  const pts=a=>a.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="#fff" stroke="#0B1F3A" stroke-width="2"><title>${escapeHTML(labels[i])}: ₱${v.toFixed(2)}</title></circle>`).join('');
  el.innerHTML=`<svg role="img" aria-label="Minimum and maximum weekly price trend chart" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">${grid}<path d="${path(low)}" fill="none" stroke="#0B1F3A" stroke-width="3" stroke-linejoin="round"/>${pts(low)}<path d="${path(high)}" fill="none" stroke="#C62828" stroke-width="3" stroke-linejoin="round"/>${high.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="3.2" fill="#C62828"><title>${escapeHTML(labels[i])}: ₱${v.toFixed(2)}</title></circle>`).join('')}${lbl}</svg>`;
}
function setupImportPreview({url,csrf}){
 const table=document.getElementById('reviewTable'),query=document.getElementById('previewSearch'),view=document.getElementById('previewView'),status=document.getElementById('previewStatus');
 const rows=[...table.querySelectorAll('tbody tr')];
 function changed(r){return r.querySelector('.row-city').value.trim()!==r.dataset.originalCity||
  r.querySelector('.row-min').value!==r.dataset.originalMin||r.querySelector('.row-max').value!==r.dataset.originalMax||
  (r.querySelector('.row-common')?.value||'')!==r.dataset.originalCommon;}
 function flag(r){return r.dataset.flagged==='1'||changed(r);}
 function updateStatus(){const pending=rows.filter(r=>r.querySelector('.row-include').checked&&flag(r)&&!r.querySelector('.row-confirm').checked).length;
  const n=document.getElementById('flagCount');if(n)n.textContent=rows.filter(flag).length;
  if(pending)status.textContent=pending+' included row(s) need confirmation before import.';
  else status.textContent='All included flagged or edited rows confirmed. Review values before importing.';}
 const reviewButton=document.getElementById('showFlagged');if(reviewButton)reviewButton.addEventListener('click',()=>{query.value='';view.value='flagged';filter();document.getElementById('reviewSection').scrollIntoView({behavior:'smooth',block:'start'});});
 function filter(){let visible=0;rows.forEach(r=>{const match=r.dataset.search.includes(query.value.trim().toLowerCase())&&(view.value==='all'||(view.value==='flagged'&&flag(r))||(view.value==='included'&&r.querySelector('.row-include').checked));r.hidden=!match;if(match)visible++;});document.getElementById('previewVisible').textContent=visible+' / '+rows.length+' shown';}
 query.addEventListener('input',filter);view.addEventListener('change',filter);filter();updateStatus();
 document.getElementById('confirmAll').addEventListener('click',()=>{rows.filter(flag).forEach(r=>r.querySelector('.row-confirm').checked=true);updateStatus();});
 document.getElementById('includeAll').addEventListener('click',()=>{rows.forEach(r=>r.querySelector('.row-include').checked=true);filter();updateStatus();});
 table.addEventListener('input',e=>{const el=e.target;if(!el.matches('.row-city,.row-min,.row-max,.row-common'))return;
  const r=el.closest('tr');r.querySelector('.row-confirm').checked=false;r.classList.add('review-row');
  if(el.matches('.row-city'))r.dataset.search=(el.value+' '+r.cells[2].textContent+' '+r.cells[3].textContent).toLowerCase();
  filter();updateStatus();});
 table.addEventListener('change',e=>{if(e.target.classList.contains('row-include'))filter();updateStatus();});
 document.getElementById('commitImport').addEventListener('click',async()=>{
  const btn=document.getElementById('commitImport');btn.disabled=true;status.textContent='Validating entries…';
  const data=rows.map(r=>({include:r.querySelector('.row-include').checked,city:r.querySelector('.row-city').value,
    min_price:r.querySelector('.row-min').value,max_price:r.querySelector('.row-max').value,
    common_price:r.querySelector('.row-common')?.value||null,confirmed:r.querySelector('.row-confirm').checked}));
  try{const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({rows:data})});
   const body=await response.json();if(!response.ok)throw Error(body.error||'Import could not be completed.');
   status.textContent='Import completed.';location.assign(body.redirect);
  }catch(err){status.textContent=err.message;btn.disabled=false;alert(err.message);}
 });
}
