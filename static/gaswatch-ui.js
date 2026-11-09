(()=>{
 const sidebar=document.getElementById('sidebar');
 const menu=document.getElementById('menuToggle');
 const shade=document.getElementById('mobileBackdrop');
 const close=()=>{sidebar?.classList.remove('mobile-open');document.body.classList.remove('nav-open');menu?.setAttribute('aria-expanded','false')};
 menu?.addEventListener('click',()=>{const active=!sidebar.classList.contains('mobile-open');sidebar.classList.toggle('mobile-open',active);document.body.classList.toggle('nav-open',active);menu.setAttribute('aria-expanded',String(active))});
 shade?.addEventListener('click',close);
 document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
})();
