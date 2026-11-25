/* Colour theme: Auto follows the OS, Light/Dark are remembered when storage works. Runs before paint. */
(function(){
  var d=document.documentElement,mq=window.matchMedia?matchMedia('(prefers-color-scheme: light)'):null,pref=null;
  try{pref=localStorage.getItem('we-theme')}catch(e){}
  if(pref!=='light'&&pref!=='dark')pref='auto';
  function apply(){
    d.dataset.theme=pref==='auto'?(mq&&mq.matches?'light':'dark'):pref;
    var b=document.querySelectorAll('#theme-switch [data-theme-pref]');
    for(var i=0;i<b.length;i++)b[i].setAttribute('aria-pressed',String(b[i].getAttribute('data-theme-pref')===pref));
  }
  apply();
  if(mq){var f=function(){if(pref==='auto')apply()};if(mq.addEventListener)mq.addEventListener('change',f);else if(mq.addListener)mq.addListener(f)}
  document.addEventListener('DOMContentLoaded',function(){
    var box=document.getElementById('theme-switch');if(!box)return;apply();
    box.addEventListener('click',function(e){
      var btn=e.target.closest('[data-theme-pref]');if(!btn)return;pref=btn.getAttribute('data-theme-pref');
      try{if(pref==='auto')localStorage.removeItem('we-theme');else localStorage.setItem('we-theme',pref)}catch(err){}
      apply();
    });
  });
})();
