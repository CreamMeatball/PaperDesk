export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

// Every request carries X-Paperdesk so the local server can reject requests from other websites.
export class ApiClient {
  async request(method, path, body, headers) {
    var options = { method: method, headers: Object.assign({ "X-Paperdesk": "1" }, headers || {}) };
    if (body !== undefined) {
      if (body instanceof Blob || body instanceof ArrayBuffer) {
        options.body = body;
      } else {
        options.body = JSON.stringify(body);
        options.headers["Content-Type"] = "application/json";
      }
    }
    var response;
    try {
      response = await fetch(path, options);
    } catch (error) {
      throw new ApiError("앱 서버에 연결하지 못했어요.", 0, "offline");
    }
    var data = null;
    try { data = await response.json(); } catch (error) { data = null; }
    if (!response.ok) {
      var detail = data && data.error ? data.error : {};
      throw new ApiError(detail.message || "요청에 실패했어요 (" + response.status + ")", response.status, detail.code);
    }
    return data;
  }

  get(path) { return this.request("GET", path); }
  post(path, body) { return this.request("POST", path, body === undefined ? {} : body); }
  put(path, body) { return this.request("PUT", path, body); }
  patch(path, body) { return this.request("PATCH", path, body); }
  del(path) { return this.request("DELETE", path); }

  upload(file, folderId) {
    var query = folderId ? "?folder=" + encodeURIComponent(folderId) : "";
    return this.request("POST", "/api/documents" + query, file,
      { "Content-Type": "application/pdf", "X-Filename": encodeURIComponent(file.name) });
  }
}

