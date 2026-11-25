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
/* save a text file: via the artifact "downloads" capability when present (the viewer blocks plain downloads), else a normal download */
window.weSave=async function(name,text){
  try{var cl=window.claude&&window.claude.use?await window.claude.use("downloads"):null;
    if(cl){await cl.save({filename:name,data:text});return}}catch(e){if(e&&e.code==="declined")return}
  var a=document.createElement("a");a.href=URL.createObjectURL(new Blob([text],{type:"text/csv"}));a.download=name;document.body.appendChild(a);a.click();a.remove()};
window.weCsvWrap=function(tw){
  var box=document.createElement("div"),bar=document.createElement("div"),b=document.createElement("button");
  bar.style.cssText="display:flex;justify-content:flex-end;margin:0 0 6px";b.type="button";b.className="chip";b.textContent="Download CSV";bar.appendChild(b);
  b.onclick=function(){
    var t=tw.querySelector("table");if(!t)return;
    var esc=function(v){v=String(v==null?"":v).replace(/\s+/g," ").trim();return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v};
    var lines=[Array.prototype.map.call(t.querySelectorAll("thead th"),function(x){return esc(x.textContent)}).join(",")];
    Array.prototype.forEach.call(t.querySelectorAll("tbody tr"),function(tr){lines.push(Array.prototype.map.call(tr.children,function(td){var c=td.querySelector("code"),r=td.getAttribute("data-raw");return esc(r!==null?r:c?c.textContent:td.textContent)}).join(","))});
    var card=tw.closest(".card"),h=card&&card.querySelector("h2"),name=((h&&h.textContent)||"table").toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"")||"table";
    window.weSave(name+".csv","\ufeff"+lines.join("\r\n"));
  };
  box.appendChild(bar);box.appendChild(tw);return box};

/* phone table layout: cards (default) or a regular table, remembered per device; pages with a #view-switch get the buttons */
(function(){function g(){try{return localStorage.getItem("we-view")}catch(e){return null}}
function set(v){try{localStorage.setItem("we-view",v)}catch(e){}document.documentElement.classList.toggle("plain-tables",v==="table")}
set(g()||"cards");
document.addEventListener("DOMContentLoaded",function(){var w=document.getElementById("view-switch");if(!w)return;
function mark(){var v=document.documentElement.classList.contains("plain-tables")?"table":"cards";w.querySelectorAll("button").forEach(function(b){b.setAttribute("aria-pressed",String(b.dataset.view===v))})}
mark();w.onclick=function(e){var b=e.target.closest("button");if(!b)return;set(b.dataset.view);mark()}})})();

/* Temporarily hidden apps (testing): empty HIDDEN_PAGES to bring them back for everyone.
   Testing mode: tap the words "Supported by" in the footer 5 times to show them on this device (tap 5 times again to hide). */
var HIDDEN_PAGES=["company.html","ask.html"];
(function(){
var dev=false;try{dev=localStorage.getItem("we-dev")==="1"}catch(e){}
var here=(location.pathname.split("/").pop()||"index.html");
if(!dev&&HIDDEN_PAGES.indexOf(here)>=0){location.replace("index.html");return}
document.addEventListener("DOMContentLoaded",function(){
  if(!dev)document.querySelectorAll("#apps a[data-dev]").forEach(function(a){a.remove()});
  if(!dev)HIDDEN_PAGES.forEach(function(h){document.querySelectorAll('#apps a[href="'+h+'"]').forEach(function(a){a.remove()})});
  var f=document.querySelector(".site-foot"),n=0,t=0;if(!f)return;
  f.addEventListener("click",function(e){if(e.target.closest("a"))return;var now=Date.now();n=now-t>4000?1:n+1;t=now;
    if(n>=5){n=0;try{localStorage.setItem("we-dev",dev?"0":"1")}catch(x){}f.firstChild.textContent=dev?"Testing mode off. ":"Testing mode on. ";setTimeout(function(){location.reload()},700)}})})})();
