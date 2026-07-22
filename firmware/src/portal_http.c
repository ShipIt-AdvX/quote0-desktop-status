#include "portal_http.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "image_store.h"
#include "lwip/ip4_addr.h"
#include "uc8251d_minimal.h"

static const char *TAG = "portal";
static desk_config_t *s_cfg;
static httpd_handle_t s_httpd;
static uint8_t s_img_tmp[IMAGE_BYTES];

/* Compact config page. Browser dither → raw 5624-byte upload (no PNG decode on device). */
static const char INDEX_HTML[] =
    "<!doctype html><html lang=zh-CN><head><meta charset=utf-8>"
    "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
    "<title>Quote/0</title>"
    "<style>"
    "body{font:15px/1.45 system-ui,sans-serif;margin:1rem;max-width:40rem;background:#f6f3ec;color:#111}"
    "h1{font-size:1.25rem;margin:0 0 .5rem}section{background:#fff;border:1px solid #ddd;padding:.8rem;margin:.7rem 0}"
    "input,button{font:inherit;padding:.4rem .55rem;margin:.2rem 0}button{background:#0b5fff;color:#fff;border:0}"
    ".s{font-size:.85rem;opacity:.85}code{background:#eee;padding:0 .25rem}.ok{color:#1a7a3c}.err{color:#b33}"
    "ul{padding-left:1.1rem}img{border:1px solid #ccc;image-rendering:pixelated}"
    "</style></head><body>"
    "<h1>Quote/0 设备配置</h1>"
    "<p class=s>本页运行在设备上 · 连接 WiFi <code>Quote0-CFG</code> 后打开 <code>http://0.1.2.3</code></p>"
    "<section><h2>状态</h2><pre id=st class=s></pre></section>"
    "<section><h2>WiFi</h2><ul id=wl></ul>"
    "<div><input id=ssid placeholder=SSID> <input id=pass placeholder=密码可空>"
    "<button onclick=addWifi()>添加</button></div></section>"
    "<section><h2>服务端</h2>"
    "<div><input id=host placeholder=\"电脑局域网IP\"> <input id=port type=number value=8787 style=width:5rem>"
    "<button onclick=setSrv()>写入</button></div>"
    "<p class=s>不要填 0.1.2.3（那是本配置页）</p></section>"
    "<section><h2>墨水屏图片</h2>"
    "<input type=file id=file accept=image/*> <label><input type=checkbox id=inv>反色</label>"
    "<button onclick=upImg()>上传显示</button>"
    "<div><button onclick=mode('image')>只用图片</button> <button onclick=mode('server')>拉PC状态</button>"
    "<button onclick=clrImg()>清除</button></div>"
    "<p><canvas id=cv width=152 height=296 style=display:none></canvas>"
    "<img id=prev width=152 height=296></p></section>"
    "<section><button onclick=save()>保存</button> <button onclick=reboot()>重启</button>"
    "<span id=msg class=s></span></section>"
    "<script>"
    "const W=152,H=296,N=(W*H)/8;"
    "async function j(u,o){const r=await fetch(u,o);const t=await r.text();let x;try{x=JSON.parse(t)}catch(e){throw new Error(t||r.status)}"
    "if(!r.ok||x.ok===false)throw new Error(x.error||t);return x}"
    "function msg(t,ok){msgEl=document.getElementById('msg');msgEl.textContent=t;msgEl.className='s '+(ok?'ok':'err')}"
    "async function refresh(){const x=await j('/api/status');st.textContent=JSON.stringify(x,null,2);"
    "wl.innerHTML=(x.wifi||[]).map(w=>'<li>'+w.ssid+(w.has_pass?' 🔒':'')+"
    "' <button onclick=\"delWifi(\\''+w.ssid.replace(/'/g,\"\\\\'\")+\"\\')\">删</button></li>').join('')||'<li>(空)</li>';"
    "if(x.server_host)host.value=x.server_host;if(x.server_port)port.value=x.server_port}"
    "async function addWifi(){await j('/api/wifi',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({ssid:ssid.value,password:pass.value})});pass.value='';await refresh();msg('已添加',1)}"
    "async function delWifi(s){await j('/api/wifi?ssid='+encodeURIComponent(s),{method:'DELETE'});await refresh();msg('已删',1)}"
    "async function setSrv(){await j('/api/server',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({host:host.value,port:+port.value})});await refresh();msg('服务端已写',1)}"
    "async function mode(m){await j('/api/mode',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({mode:m})});await refresh();msg('模式 '+m,1)}"
    "async function save(){await j('/api/save',{method:'POST'});msg('已保存',1)}"
    "async function reboot(){await j('/api/reboot',{method:'POST'});msg('重启中…',1)}"
    "async function clrImg(){await j('/api/image',{method:'DELETE'});await refresh();msg('已清除',1)}"
    "function toFrame(img,inv){const c=cv.getContext('2d');c.fillStyle='#fff';c.fillRect(0,0,W,H);"
    "const r=Math.max(W/img.width,H/img.height);const dw=img.width*r,dh=img.height*r;"
    "c.drawImage(img,(W-dw)/2,(H-dh)/2,dw,dh);const d=c.getImageData(0,0,W,H).data;"
    "const g=new Float32Array(W*H);for(let i=0;i<W*H;i++){const o=i*4;g[i]=(d[o]*0.299+d[o+1]*0.587+d[o+2]*0.114)/255}"
    "const out=new Uint8Array(N);for(let y=0;y<H;y++)for(let x=0;x<W;x++){let i=y*W+x,v=g[i],nv=v>0.5?1:0,e=v-nv;"
    "if(x+1<W)g[i+1]+=e*7/16;if(y+1<H){if(x>0)g[i+W-1]+=e*3/16;g[i+W]+=e*5/16;if(x+1<W)g[i+W+1]+=e*1/16}"
    "let white=!!nv;if(inv)white=!white;if(white){const bi=(y*W+x)>>3,bit=7-((y*W+x)&7);out[bi]|=1<<bit}}"
    "prev.src=cv.toDataURL();return out}"
    "async function upImg(){const f=file.files[0];if(!f){msg('选图片',0);return}"
    "const url=URL.createObjectURL(f);const img=new Image();await new Promise((res,rej)=>{img.onload=res;img.onerror=rej;img.src=url});"
    "const bin=toFrame(img,inv.checked);URL.revokeObjectURL(url);"
    "const r=await fetch('/api/image',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:bin});"
    "const x=await r.json();if(!r.ok||x.ok===false)throw new Error(x.error||'fail');await refresh();msg('图片已显示',1)}"
    "refresh().catch(e=>msg(e.message,0))"
    "</script></body></html>";

static esp_err_t send_json(httpd_req_t *req, int code, const char *json)
{
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_status(req, code == 200 ? HTTPD_200 : "400 Bad Request");
    return httpd_resp_send(req, json, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t send_json_ok(httpd_req_t *req, const char *extra)
{
    char buf[192];
    if (extra && extra[0]) {
        snprintf(buf, sizeof(buf), "{\"ok\":true,%s}", extra);
    } else {
        snprintf(buf, sizeof(buf), "{\"ok\":true}");
    }
    return send_json(req, 200, buf);
}

static esp_err_t send_json_err(httpd_req_t *req, const char *err)
{
    char buf[192];
    snprintf(buf, sizeof(buf), "{\"ok\":false,\"error\":\"%s\"}", err ? err : "error");
    return send_json(req, 400, buf);
}

static esp_err_t root_get(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t status_get(httpd_req_t *req)
{
    char wifi_part[512] = {0};
    size_t off = 0;
    wifi_part[off++] = '[';
    for (uint8_t i = 0; i < s_cfg->wifi_count && off + 80 < sizeof(wifi_part); i++) {
        if (i) {
            wifi_part[off++] = ',';
        }
        int n = snprintf(wifi_part + off, sizeof(wifi_part) - off,
                         "{\"ssid\":\"%s\",\"has_pass\":%s}", s_cfg->wifi[i].ssid,
                         s_cfg->wifi[i].pass[0] ? "true" : "false");
        if (n > 0) {
            off += (size_t)n;
        }
    }
    if (off < sizeof(wifi_part)) {
        wifi_part[off++] = ']';
        wifi_part[off] = '\0';
    }

    char buf[768];
    snprintf(buf, sizeof(buf),
             "{\"ok\":true,\"wifi\":%s,\"server_host\":\"%s\",\"server_port\":%u,\"poll_sec\":%u,"
             "\"has_image\":%s,\"show_custom_image\":%u}",
             wifi_part, s_cfg->server_host, s_cfg->server_port, s_cfg->poll_sec,
             image_store_has() ? "true" : "false", (unsigned)s_cfg->show_custom_image);
    return send_json(req, 200, buf);
}

static bool read_body(httpd_req_t *req, char *buf, size_t cap)
{
    int total = req->content_len;
    if (total < 0 || (size_t)total >= cap) {
        return false;
    }
    int got = 0;
    while (got < total) {
        int r = httpd_req_recv(req, buf + got, total - got);
        if (r <= 0) {
            return false;
        }
        got += r;
    }
    buf[got] = '\0';
    return true;
}

static esp_err_t wifi_post(httpd_req_t *req)
{
    char body[192];
    if (!read_body(req, body, sizeof(body))) {
        return send_json_err(req, "body");
    }
    char ssid[CFG_SSID_MAX] = {0};
    char pass[CFG_PASS_MAX] = {0};
    /* very small JSON parse */
    char *p = strstr(body, "\"ssid\"");
    if (!p) {
        return send_json_err(req, "need ssid");
    }
    p = strchr(p + 6, '"');
    if (!p) {
        return send_json_err(req, "ssid");
    }
    p++;
    char *e = strchr(p, '"');
    if (!e) {
        return send_json_err(req, "ssid");
    }
    size_t n = (size_t)(e - p);
    if (n >= sizeof(ssid)) {
        n = sizeof(ssid) - 1;
    }
    memcpy(ssid, p, n);
    p = strstr(e, "\"password\"");
    if (p) {
        p = strchr(p + 10, '"');
        if (p) {
            p++;
            e = strchr(p, '"');
            if (e) {
                n = (size_t)(e - p);
                if (n >= sizeof(pass)) {
                    n = sizeof(pass) - 1;
                }
                memcpy(pass, p, n);
            }
        }
    }
    if (!config_wifi_add(s_cfg, ssid, pass)) {
        return send_json_err(req, "wifi full");
    }
    return send_json_ok(req, NULL);
}

static esp_err_t wifi_delete(httpd_req_t *req)
{
    char q[96] = {0};
    if (httpd_req_get_url_query_str(req, q, sizeof(q)) != ESP_OK) {
        return send_json_err(req, "need ssid");
    }
    char ssid[CFG_SSID_MAX] = {0};
    if (httpd_query_key_value(q, "ssid", ssid, sizeof(ssid)) != ESP_OK) {
        return send_json_err(req, "need ssid");
    }
    if (!config_wifi_del(s_cfg, ssid)) {
        return send_json_err(req, "not found");
    }
    return send_json_ok(req, NULL);
}

static esp_err_t server_post(httpd_req_t *req)
{
    char body[160];
    if (!read_body(req, body, sizeof(body))) {
        return send_json_err(req, "body");
    }
    char host[CFG_HOST_MAX] = {0};
    unsigned port = 8787;
    char *p = strstr(body, "\"host\"");
    if (!p) {
        return send_json_err(req, "need host");
    }
    p = strchr(p + 6, '"');
    if (!p) {
        return send_json_err(req, "host");
    }
    p++;
    char *e = strchr(p, '"');
    if (!e) {
        return send_json_err(req, "host");
    }
    size_t n = (size_t)(e - p);
    if (n >= sizeof(host)) {
        n = sizeof(host) - 1;
    }
    memcpy(host, p, n);
    p = strstr(body, "\"port\"");
    if (p) {
        p = strchr(p, ':');
        if (p) {
            port = (unsigned)atoi(p + 1);
        }
    }
    if (port == 0 || port > 65535) {
        port = 8787;
    }
    strncpy(s_cfg->server_host, host, sizeof(s_cfg->server_host) - 1);
    s_cfg->server_port = (uint16_t)port;
    return send_json_ok(req, NULL);
}

static esp_err_t mode_post(httpd_req_t *req)
{
    char body[64];
    if (!read_body(req, body, sizeof(body))) {
        return send_json_err(req, "body");
    }
    if (strstr(body, "image")) {
        s_cfg->show_custom_image = 1;
    } else {
        s_cfg->show_custom_image = 0;
    }
    return send_json_ok(req, NULL);
}

static esp_err_t save_post(httpd_req_t *req)
{
    return config_save(s_cfg) ? send_json_ok(req, NULL) : send_json_err(req, "save failed");
}

static esp_err_t reboot_post(httpd_req_t *req)
{
    send_json_ok(req, NULL);
    vTaskDelay(pdMS_TO_TICKS(300));
    esp_restart();
    return ESP_OK;
}

static esp_err_t image_post(httpd_req_t *req)
{
    if (req->content_len != IMAGE_BYTES) {
        return send_json_err(req, "need 5624 bytes");
    }
    int got = 0;
    while (got < IMAGE_BYTES) {
        int r = httpd_req_recv(req, (char *)s_img_tmp + got, IMAGE_BYTES - got);
        if (r <= 0) {
            return send_json_err(req, "recv");
        }
        got += r;
    }
    if (!image_store_save(s_img_tmp, IMAGE_BYTES)) {
        return send_json_err(req, "nvs");
    }
    s_cfg->show_custom_image = 1;
    config_save(s_cfg);
    uc8251d_display(s_img_tmp);
    return send_json_ok(req, NULL);
}

static esp_err_t image_delete(httpd_req_t *req)
{
    image_store_clear();
    s_cfg->show_custom_image = 0;
    config_save(s_cfg);
    return send_json_ok(req, NULL);
}

static void start_httpd(void)
{
    if (s_httpd) {
        return;
    }
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.lru_purge_enable = true;
    config.max_uri_handlers = 16;
    config.stack_size = 8192;
    if (httpd_start(&s_httpd, &config) != ESP_OK) {
        ESP_LOGE(TAG, "httpd_start failed");
        s_httpd = NULL;
        return;
    }

    const httpd_uri_t uris[] = {
        {.uri = "/", .method = HTTP_GET, .handler = root_get},
        {.uri = "/api/status", .method = HTTP_GET, .handler = status_get},
        {.uri = "/api/wifi", .method = HTTP_POST, .handler = wifi_post},
        {.uri = "/api/wifi", .method = HTTP_DELETE, .handler = wifi_delete},
        {.uri = "/api/server", .method = HTTP_POST, .handler = server_post},
        {.uri = "/api/mode", .method = HTTP_POST, .handler = mode_post},
        {.uri = "/api/save", .method = HTTP_POST, .handler = save_post},
        {.uri = "/api/reboot", .method = HTTP_POST, .handler = reboot_post},
        {.uri = "/api/image", .method = HTTP_POST, .handler = image_post},
        {.uri = "/api/image", .method = HTTP_DELETE, .handler = image_delete},
    };
    for (size_t i = 0; i < sizeof(uris) / sizeof(uris[0]); i++) {
        httpd_register_uri_handler(s_httpd, &uris[i]);
    }
    ESP_LOGI(TAG, "HTTP portal on http://0.1.2.3/");
}

static void configure_softap_ip(void)
{
    esp_netif_t *ap = esp_netif_get_handle_from_ifkey("WIFI_AP_DEFAULT");
    if (!ap) {
        ESP_LOGE(TAG, "no AP netif");
        return;
    }
    esp_netif_dhcps_stop(ap);
    esp_netif_ip_info_t ip_info = {0};
    IP4_ADDR(&ip_info.ip, 0, 1, 2, 3);
    IP4_ADDR(&ip_info.gw, 0, 1, 2, 3);
    IP4_ADDR(&ip_info.netmask, 255, 255, 255, 0);
    ESP_ERROR_CHECK(esp_netif_set_ip_info(ap, &ip_info));
    ESP_ERROR_CHECK(esp_netif_dhcps_start(ap));
    ESP_LOGI(TAG, "SoftAP IP 0.1.2.3");
}

bool portal_start(desk_config_t *cfg)
{
    s_cfg = cfg;
    start_httpd();
    return s_httpd != NULL;
}

void portal_set_cfg(desk_config_t *cfg)
{
    s_cfg = cfg;
}

void portal_httpd_start(void)
{
    start_httpd();
}

void portal_httpd_stop(void)
{
    if (s_httpd) {
        httpd_stop(s_httpd);
        s_httpd = NULL;
        ESP_LOGI(TAG, "HTTP portal stopped");
    }
}

void portal_configure_softap_ip(void)
{
    configure_softap_ip();
}

void portal_attach_after_wifi(desk_config_t *cfg)
{
    s_cfg = cfg;
    configure_softap_ip();
    start_httpd();
}
