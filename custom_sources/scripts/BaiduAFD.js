// Keep Baidu's expected JSON envelope while removing the delivered ad list.
let body = $response.body;

try {
  const payload = JSON.parse(body);
  if (payload && payload.res && Array.isArray(payload.res.ad)) {
    payload.res.ad = [];
    body = JSON.stringify(payload);
  }
} catch (error) {
  console.log(`[BaiduAFD] ${error}`);
}

$done({ body });
