"""Đại số tuyến tính tối thiểu, Python thuần — nền cho lớp mô hình.

VÌ SAO TỰ VIẾT THAY VÌ DÙNG NUMPY:
  - Bài toán ở đây nhỏ: 8 chiều, vài chục nghìn dòng. Python thuần thừa nhanh.
  - Máy chủ chạy sản phẩm không phải cài thêm gì. Triển khai nhẹ là một yêu cầu
    thật của dự án này, không phải sở thích.
  - Mọi bước đều đọc và kiểm tra được. Với phần mềm cảnh báo thiên tai, thứ
    không giải thích được thì không nên tin.

CẢNH BÁO SỐ HỌC: ma trận hiệp phương sai của dữ liệu khí tượng gần suy biến —
mưa và độ ẩm đi cùng nhau, nhiệt và bức xạ đi cùng nhau. Nghịch đảo thẳng sẽ
nổ. Vì vậy luôn cộng một lượng nhỏ vào đường chéo (ridge) trước khi nghịch đảo,
và hàm inverse() từ chối trả kết quả nếu phát hiện trụ xoay quá nhỏ.
"""
from __future__ import annotations

Matrix = list[list[float]]
Vector = list[float]


def mean(rows: list[Vector]) -> Vector:
    n = len(rows)
    if n == 0:
        raise ValueError("mean() cần ít nhất một dòng")
    d = len(rows[0])
    out = [0.0] * d
    for r in rows:
        for j in range(d):
            out[j] += r[j]
    return [v / n for v in out]


def stdev(rows: list[Vector], mu: Vector) -> Vector:
    """Độ lệch chuẩn mẫu. Sàn 1e-9 để cột hằng số không gây chia cho 0."""
    n = len(rows)
    if n < 2:
        return [1.0] * len(mu)
    d = len(mu)
    acc = [0.0] * d
    for r in rows:
        for j in range(d):
            dv = r[j] - mu[j]
            acc[j] += dv * dv
    return [max((v / (n - 1)) ** 0.5, 1e-9) for v in acc]


def zscore(row: Vector, mu: Vector, sd: Vector) -> Vector:
    return [(row[j] - mu[j]) / sd[j] for j in range(len(row))]


def covariance(rows: list[Vector]) -> Matrix:
    """Hiệp phương sai mẫu (chia n-1). Giả định rows đã được chuẩn hoá z."""
    n = len(rows)
    if n < 2:
        raise ValueError("covariance() cần ít nhất hai dòng")
    d = len(rows[0])
    mu = mean(rows)
    cov = [[0.0] * d for _ in range(d)]
    for r in rows:
        dv = [r[j] - mu[j] for j in range(d)]
        for i in range(d):
            di = dv[i]
            if di == 0.0:
                continue
            ci = cov[i]
            for j in range(i, d):
                ci[j] += di * dv[j]
    for i in range(d):
        for j in range(i, d):
            v = cov[i][j] / (n - 1)
            cov[i][j] = v
            cov[j][i] = v
    return cov


def ridge(cov: Matrix, strength: float = 1e-4) -> Matrix:
    """Cộng λ vào đường chéo, λ tỉ lệ với vết ma trận.

    Không dùng hằng số tuyệt đối: nếu dữ liệu đã chuẩn hoá z thì vết ≈ d, nhưng
    hàm này cũng phải đúng khi ai đó đưa vào dữ liệu chưa chuẩn hoá.
    """
    d = len(cov)
    trace = sum(cov[i][i] for i in range(d))
    lam = max(strength * trace / d, 1e-12)
    return [
        [cov[i][j] + (lam if i == j else 0.0) for j in range(d)]
        for i in range(d)
    ]


def inverse(m: Matrix) -> Matrix | None:
    """Nghịch đảo bằng Gauss-Jordan có chọn trụ xoay từng phần.

    Trả None khi ma trận suy biến trong phạm vi số học — gọi hàm phải xử lý,
    KHÔNG được coi None là ma trận đơn vị. Một mô hình không nghịch đảo được
    hiệp phương sai là mô hình chưa dùng được, và nó phải nói ra điều đó.
    """
    d = len(m)
    a = [list(m[i]) + [1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]
    for col in range(d):
        piv = max(range(col, d), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        if piv != col:
            a[col], a[piv] = a[piv], a[col]
        pv = a[col][col]
        row = a[col]
        for j in range(col, 2 * d):
            row[j] /= pv
        for r in range(d):
            if r == col:
                continue
            f = a[r][col]
            if f == 0.0:
                continue
            ar = a[r]
            for j in range(col, 2 * d):
                ar[j] -= f * row[j]
    return [r[d:] for r in a]


def mahalanobis_sq(x: Vector, mu: Vector, inv: Matrix) -> float:
    """Khoảng cách Mahalanobis bình phương.

    Đây là chỗ mô hình khác hẳn cách xét từng biến một: nó tính độ bất thường
    của TỔ HỢP, sau khi đã trừ đi phần tương quan mà khí hậu vốn có. Mưa 80 mm
    là bình thường; đất đã bão hoà là bình thường; hai thứ cùng lúc thì không.
    """
    d = len(mu)
    dv = [x[j] - mu[j] for j in range(d)]
    total = 0.0
    for i in range(d):
        di = dv[i]
        if di == 0.0:
            continue
        row = inv[i]
        s = 0.0
        for j in range(d):
            s += row[j] * dv[j]
        total += di * s
    return max(total, 0.0)


def percentile_of(sorted_vals: list[float], v: float) -> float:
    """Vị trí của v trong một dãy ĐÃ SẮP XẾP, tính theo phần trăm 0–100.

    Dùng phân bố kinh nghiệm chứ không giả định chi-bình-phương: dữ liệu khí
    tượng có đuôi dày hơn Gaussian, nên giả định lý thuyết sẽ đánh giá thấp
    mức hiếm của những ngày cực đoan — đúng những ngày ta cần bắt.
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] <= v:
            lo = mid + 1
        else:
            hi = mid
    return 100.0 * lo / n


def quantile(sorted_vals: list[float], q: float) -> float:
    """Phân vị q (0–100) bằng nội suy tuyến tính giữa hai điểm gần nhất."""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("quantile() cần dữ liệu")
    if n == 1:
        return sorted_vals[0]
    pos = (q / 100.0) * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac
