/* KIỂM ẢNH RUỘNG NGAY TRÊN MÁY — không cần mạng (nâng cấp 25/11/2026).
 *
 * Chạy đúng mô hình máy chủ đang dùng (SegFormer-b0 "nước trong ảnh thực địa", bản v2 đã qua cổng ảnh lũ + đối chứng
 * ruộng khô — backend/data/ml/field_water_v2_result.json) bằng onnxruntime-web (WebAssembly) ngay trong trình duyệt.
 * Tiền xử lý GIỐNG HỆT backend/app/services/field_water.py: 512×512, /255, chuẩn hoá ImageNet, CHW; nước = lớp 1 của
 * argmax trên lưới 128×128. Ảnh KHÔNG rời máy.
 *
 * Mô hình (16 MB) + runtime (~11 MB) chỉ tải khi người dùng bấm lần đầu; service worker giữ lại → lần sau chạy được cả khi
 * mất sóng giữa ruộng. Dùng chung cho thẻ trong ứng dụng và trang offline.html: window.ttFieldCheck(file) → Promise.
 */
(function () {
  var MODEL = "/models/field_water.onnx";
  var SIZE = 512, MEAN = [0.485, 0.456, 0.406], STD = [0.229, 0.224, 0.225];
  var sessP = null;

  function loadOrt() {
    if (window.ort) return Promise.resolve(window.ort);
    return new Promise(function (ok, bad) {
      var s = document.createElement("script");
      s.src = "/ort/ort.wasm.min.js";
      s.onload = function () { ok(window.ort); };
      s.onerror = function () { bad(new Error("Không tải được bộ chạy AI (cần mạng ở lần đầu).")); };
      document.head.appendChild(s);
    });
  }

  function session() {
    if (!sessP) {
      sessP = loadOrt().then(function (ort) {
        ort.env.wasm.wasmPaths = "/ort/";
        ort.env.wasm.numThreads = 1;          // không cần cross-origin isolation; điện thoại phổ thông vẫn chạy
        return ort.InferenceSession.create(MODEL, { executionProviders: ["wasm"] });
      }).catch(function (e) { sessP = null; throw e; });
    }
    return sessP;
  }

  function toTensor(img) {
    var c = document.createElement("canvas");
    c.width = SIZE; c.height = SIZE;
    var g = c.getContext("2d");
    g.imageSmoothingEnabled = true;
    g.imageSmoothingQuality = "medium";       // gần BILINEAR của Pillow phía máy chủ
    g.drawImage(img, 0, 0, SIZE, SIZE);
    var px = g.getImageData(0, 0, SIZE, SIZE).data;
    var n = SIZE * SIZE, out = new Float32Array(3 * n);
    for (var i = 0; i < n; i++) {
      for (var k = 0; k < 3; k++) out[k * n + i] = (px[i * 4 + k] / 255 - MEAN[k]) / STD[k];
    }
    return out;
  }

  function readImage(file) {
    return new Promise(function (ok, bad) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); ok(img); };
      img.onerror = function () { URL.revokeObjectURL(url); bad(new Error("Không đọc được ảnh.")); };
      img.src = url;
    });
  }

  window.ttFieldCheck = function (file) {
    var t0 = performance.now();
    return Promise.all([session(), readImage(file)]).then(function (r) {
      var sess = r[0], ort = window.ort;
      var x = new ort.Tensor("float32", toTensor(r[1]), [1, 3, SIZE, SIZE]);
      return sess.run({ image: x }).then(function (o) {
        var lg = o.logits.data, hw = o.logits.dims[2] * o.logits.dims[3], water = 0;
        for (var i = 0; i < hw; i++) if (lg[hw + i] > lg[i]) water++;   // argmax 2 lớp: lớp 1 = nước
        return { ratio: Math.round((water / hw) * 1000) / 1000, ms: Math.round(performance.now() - t0), offline: !navigator.onLine };
      });
    });
  };
  window.ttFieldCheckReady = function () { return session().then(function () { return true; }); };
  // Kiểm tương đương với máy chủ (ops): biên logit "nước − không nước" từng ô 128×128.
  window.ttFieldCheckMargins = function (file) {
    return Promise.all([session(), readImage(file)]).then(function (r) {
      var x = new window.ort.Tensor("float32", toTensor(r[1]), [1, 3, SIZE, SIZE]);
      return r[0].run({ image: x }).then(function (o) {
        var lg = o.logits.data, hw = o.logits.dims[2] * o.logits.dims[3], m = new Array(hw);
        for (var i = 0; i < hw; i++) m[i] = lg[hw + i] - lg[i];
        return m;
      });
    });
  };
})();
