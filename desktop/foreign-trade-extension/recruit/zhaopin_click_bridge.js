'use strict';

const REQUEST_SOURCE = 'companyleads:zhaopin-click-request';
const RESPONSE_SOURCE = 'companyleads:zhaopin-click-response';

window.addEventListener('message', event => {
  if (event.source !== window) return;
  const data = event.data || {};
  if (data.source !== REQUEST_SOURCE || !data.requestId) return;

  chrome.runtime.sendMessage({
    type: 'zhaopin:debugger_click',
    requestId: data.requestId,
    x: data.x,
    y: data.y,
  }).then(response => {
    window.postMessage({
      source: RESPONSE_SOURCE,
      requestId: data.requestId,
      response: response || { ok: false, reason: 'empty_response' },
    }, '*');
  }).catch(err => {
    window.postMessage({
      source: RESPONSE_SOURCE,
      requestId: data.requestId,
      response: { ok: false, reason: err?.message || String(err) },
    }, '*');
  });
});
