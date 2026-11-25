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

/* CSV export for any table: weCsvWrap(tableWrapper) returns a node with a "CSV" button above it */
window.weCsvWrap=function(tw){
  var box=document.createElement("div"),bar=document.createElement("div"),b=document.createElement("button");
  bar.style.cssText="display:flex;justify-content:flex-end;margin:0 0 6px";b.type="button";b.className="chip";b.textContent="Download CSV";bar.appendChild(b);
  b.onclick=function(){
    var t=tw.querySelector("table");if(!t)return;
    var esc=function(v){v=String(v==null?"":v).replace(/\s+/g," ").trim();return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v};
    var lines=[Array.prototype.map.call(t.querySelectorAll("thead th"),function(x){return esc(x.textContent)}).join(",")];
    Array.prototype.forEach.call(t.querySelectorAll("tbody tr"),function(tr){lines.push(Array.prototype.map.call(tr.children,function(td){var c=td.querySelector("code"),r=td.getAttribute("data-raw");return esc(r!==null?r:c?c.textContent:td.textContent)}).join(","))});
    var card=tw.closest(".card"),h=card&&card.querySelector("h2"),name=((h&&h.textContent)||"table").toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"")||"table";
    var a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["﻿"+lines.join("\r\n")],{type:"text/csv"}));a.download=name+".csv";document.body.appendChild(a);a.click();a.remove();
  };
  box.appendChild(bar);box.appendChild(tw);return box};

/* phone table layout: cards (default) or a regular table, remembered per device; pages with a #view-switch get the buttons */
(function(){function g(){try{return localStorage.getItem("we-view")}catch(e){return null}}
function set(v){try{localStorage.setItem("we-view",v)}catch(e){}document.documentElement.classList.toggle("plain-tables",v==="table")}
set(g()||"cards");
document.addEventListener("DOMContentLoaded",function(){var w=document.getElementById("view-switch");if(!w)return;
function mark(){var v=document.documentElement.classList.contains("plain-tables")?"table":"cards";w.querySelectorAll("button").forEach(function(b){b.setAttribute("aria-pressed",String(b.dataset.view===v))})}
mark();w.onclick=function(e){var b=e.target.closest("button");if(!b)return;set(b.dataset.view);mark()}})})();
