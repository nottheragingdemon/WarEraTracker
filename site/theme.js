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
   Testing mode: tap the footer line at the bottom of the page 5 times to show them on this device (tap 5 times again to hide). */
var HIDDEN_PAGES=["ask.html"];
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


/* amber banner when the data on the page is more than 2 hours old (the hourly refresh failed or was skipped, or the page is a stale copy) */
window.weStale=function(generated){
  var h=(Date.now()-Date.parse(generated))/36e5;if(!(h>2))return;
  var m=document.getElementById("meta");if(!m)return;
  var d=document.createElement("div");d.className="stale-banner";d.setAttribute("role","status");
  d.textContent="⚠ Data is "+(h<48?Math.round(h)+" h":Math.round(h/24)+" days")+" old (updated "+String(generated).slice(0,16).replace("T"," ")+" UTC). The hourly refresh may have failed or been skipped, so recent battles and money may be missing.";
  m.insertAdjacentElement("afterend",d)};

/* per-battle stats arrive packed as [[kind, battle, [entity*3+side, value, ...]], ...]: unpack to rows [kind, battle, entity, side, value] */
window.weStats=function(D){if(D.stats)return D.stats;var out=[];(D.statsP||[]).forEach(function(g){var k=g[0],b=g[1],f=g[2];for(var i=0;i<f.length;i+=2){var x=f[i];out.push([k,b,(x-x%3)/3,x%3,f[i+1]])}});return out};

/* phones: the app tabs scroll sideways; keep the current app in view and fade the edge that has more tabs */
document.addEventListener("DOMContentLoaded",function(){var n=document.getElementById("apps");if(!n)return;
  var cur=n.querySelector("[aria-current]");if(cur&&n.scrollWidth>n.clientWidth)n.scrollLeft=Math.max(0,cur.offsetLeft-(n.clientWidth-cur.offsetWidth)/2);
  function edge(){n.classList.toggle("more-right",n.scrollLeft+n.clientWidth<n.scrollWidth-4);n.classList.toggle("more-left",n.scrollLeft>4)}
  edge();n.addEventListener("scroll",edge,{passive:true});addEventListener("resize",edge)});

/* company-data.json stores region ids and item codes as indexes (regionKeys, items) to keep the file small: map them back */
window.weUnpackCompanies=function(cx){if(!cx||cx.__unpacked)return cx;var rk=cx.regionKeys,ik=cx.items;
  if(rk||ik)(cx.companies||[]).forEach(function(c){if(ik&&typeof c[2]==="number")c[2]=ik[c[2]];if(rk&&typeof c[4]==="number")c[4]=rk[c[4]]});
  if(rk)(cx.wageHistReg||[]).forEach(function(r){if(typeof r[0]==="number")r[0]=rk[r[0]]});cx.__unpacked=true;return cx};

/* shared page helpers (each page used to carry its own copy) */
window.weEl=function(tag,attrs,kids){var e=document.createElement(tag);if(attrs)for(var k in attrs){if(k==="text")e.textContent=attrs[k];else if(k==="class")e.className=attrs[k];else e.setAttribute(k,attrs[k])}
  (kids||[]).forEach(function(c){if(c==null||c===false||c==="")return;e.appendChild(typeof c==="object"?c:document.createTextNode(String(c)))});return e};
window.weCard=function(title,kids){return weEl("div",{class:"card"},[weEl("h2",{text:title})].concat(kids||[]))};
/* KPI tiles from [value, label, optional note] */
window.weKpis=function(list){return weEl("div",{class:"kpis"},list.map(function(x){return weEl("div",{class:"kpi"},[weEl("b",{text:String(x[0])}),weEl("span",{text:x[1]}),x[2]?weEl("small",{text:x[2],style:"display:block;color:var(--muted);margin-top:2px"}):null])}))};
/* a formatted number that also carries its raw value (for sorting and CSV) */
window.weNum=function(n,d){var o=new String(n==null||isNaN(n)?"–":Number(n).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}));o.raw=n==null||isNaN(n)?"":Math.round(n*1e4)/1e4;return o};
window.weFmtD=function(s){return s?s.slice(0,16).replace("T"," "):"–"};

/* The data files carry a schema number; a page built for another one says so instead of failing with a cryptic error. */
window.WE_SCHEMA=4;
window.weSchema=function(d){
  if(!d||d.schema==null||d.schema===window.WE_SCHEMA)return;
  var older=d.schema<window.WE_SCHEMA;
  var b=document.createElement("div");b.setAttribute("role","alert");
  b.style.cssText="margin:8px 0;padding:8px 12px;border:1px solid var(--warn,#c90);border-radius:8px;background:var(--card,transparent)";
  b.textContent=older?"The data files are older than this page (schema "+d.schema+", page expects "+window.WE_SCHEMA+"). Some numbers may be missing until the next hourly update."
    :"The data files are newer than this page (schema "+d.schema+", page expects "+window.WE_SCHEMA+"). Reload the page; if this stays, the page needs updating.";
  var m=document.getElementById("meta");(m&&m.parentNode?m.parentNode:document.body).insertBefore(b,m||document.body.firstChild);
};

/* Parts of the data only some pages need live in their own files (battle-data.json: statsP; transfer-data.json: donors), so the
   others download about a third of the size. Merges the named keys into d; if the file isn't there yet, d keeps what it has. */
window.weLoad=async function(d,file,keys){
  try{var x=(window.WE_FILES&&window.WE_FILES[file])||await fetch(file).then(function(r){if(!r.ok)throw new Error(r.status);return r.json()});keys.forEach(function(k){if(x[k]!=null)d[k]=x[k]})}catch(e){}
  return d};

/* a closed-by-default section for long explanations */
window.weFold=function(title,kids){var d=document.createElement("details");d.className="fold";var s=document.createElement("summary");s.textContent=title;d.appendChild(s);kids.forEach(function(k){if(k)d.appendChild(k)});return d};
