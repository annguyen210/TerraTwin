# Diễn tập khôi phục — so số hàng từng bảng: gốc SAU sao lưu (tệp chính), gốc TRƯỚC (-v B), bản khôi phục (-v R).
  BEGIN { while ((getline l < B) > 0) { split(l, a, "\t"); b[a[1]] = a[2] }
          while ((getline l < R) > 0) { split(l, a, "\t"); r[a[1]] = a[2] } }
  { t = $1; aft = $2 + 0; tables++; rows += aft
    if (!(t in r)) { print "[drill] ❌ thiếu bảng " t " trong bản khôi phục"; bad++; next }
    bef = (t in b) ? b[t] + 0 : aft; got = r[t] + 0
    lo = (bef < aft) ? bef : aft; hi = (bef < aft) ? aft : bef
    if (got < lo || got > hi) { print "[drill] ❌ " t ": khôi phục " got ", gốc trước/sau sao lưu " bef "/" aft; bad++ }
    else if (lo != hi) { moving++ } }
  END { printf "[drill] %d bảng, %d hàng ở gốc; %d bảng đang ghi trong lúc sao lưu (chấp nhận trong khoảng trước–sau)\n", tables, rows, moving
        exit (bad > 0) }
