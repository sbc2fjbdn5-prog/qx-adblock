const url = $request.url || "";
const marker = "[CMCC_TRACE]";
const suspect = /(?:adver|advert|splash|launch|welcome|start|init|sale|market|activity|campaign|preload|material|resource|group\d+\/m00|\.(?:jpe?g|png|webp|gif|mp4)(?:\?|$))/i.test(url);

console.log(`${marker} ${suspect ? "[SUSPECT] " : ""}${url}`);

if (suspect) {
  const key = "cmcc_trace_last_suspect";
  const last = $prefs.valueForKey(key);
  if (last !== url) {
    $prefs.setValueForKey(url, key);
    $notify("中国移动疑似广告接口", "请截取 QX 日志中的完整地址", url);
  }
}

$done({});
