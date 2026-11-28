# Kế hoạch đối chiếu số liệu báo cáo QC

> **Đã xử lý trên Pilot ngày 27/11/2026.** Người dùng chọn một script cập nhật ngày của `Occurred At` cho toàn bộ event QC, thay cho phương án đổi Query Report. Kết quả và lệnh đã chạy được lưu trong [hồ sơ thực hiện](https://chatgpt.com/space/page_796490d38d5881918da741cede207813).

Mục tiêu là làm cho báo cáo QC trong `quality-control` khớp với báo cáo Power BI khi dùng cùng khoảng ngày, QC và bộ lọc. Trước khi sửa, cần xác định chênh lệch nằm ở tập event, cách ánh xạ chiều dữ liệu hay phép tính.

## Phạm vi

- Báo cáo `/desk/quality-control/qc-internal-report` và dataset `QC Internal Dataset`.
- Nguồn event Frappe `QC Inspection Event`; `UQQC` là hệ thống riêng và không thuộc đợt đối chiếu này.
- Giữ nguyên các measure DAX người dùng đã gửi cho đến khi đối chiếu chứng minh công thức cần đổi.
- Chạy một script trên dữ liệu Pilot hiện có; không thay đổi mã báo cáo hoặc UQQC.

## Bằng chứng hiện có

Đối chiếu QC1, từ 16/11/2026 đến hết 22/11/2026, không chọn thêm công ty, xưởng, chuyền hoặc mã hàng:

| Bộ số liệu | Tổng kiểm | Tổng lỗi | Hàng đạt |
| --- | ---: | ---: | ---: |
| Power BI cũ và SQL `FactoryManagementDb.dbo.QCInspections` (`Source = QC`, `IsDeleted = 0`) | 119.940 | 54.586 | 65.354 |
| Báo cáo Frappe hiện tại | 131.601 | 56.439 | 75.162 |
| Frappe trừ Power BI/SQL | +11.661 | +1.853 | +9.808 |

Khoảng 92% phần tăng số kiểm tra nằm ở Việt Vương 3: +10.767 kiểm tra, +1.302 lỗi và +9.465 hàng đạt. Kết quả kiểm tra bên dưới xác nhận phần tăng này do lấy sai ngày ở hai mép khoảng lọc.

Mã hiện tại dùng đúng quy tắc measure đã cung cấp: `CumulativeSubtract` và `CumulativeAdd` cộng vào tổng kiểm; `DefectAdd` cộng vào tổng lỗi; hàng đạt bằng tổng kiểm trừ tổng lỗi. Tỷ lệ lỗi được tính từ tổng lỗi chia tổng kiểm. Phần này nằm ở [bộ tổng hợp báo cáo](factory_management/public/js/qc_internal_report_view.js#L2) và [truy vấn dataset](factory_management/quality_control/report/qc_internal_dataset/qc_internal_dataset.json#L18).

Luồng snapshot QC chính thức trong [source refresh](factory_management/source_refresh.py#L148) từ chối dòng có `IsDeleted` hoặc `Source` khác `QC`, rồi kiểm tra tập `event_uid` Frappe có khớp snapshot hay không. Luồng này lưu `OccurredAt` ở UTC và tạo `server_date_key` theo múi giờ của site. [Truy vấn dataset](factory_management/quality_control/report/qc_internal_dataset/qc_internal_dataset.json#L18) hiện bỏ qua trường ngày địa phương này.

Trang `QC Inspection Event` đang mở có bộ lọc **Created On: Last 90 Days** và chỉ hiển thị 20 trên hơn 1.000 bản ghi. Bộ lọc đó không giới hạn theo `Occurred At` của tuần đang so sánh nên danh sách hiện tại chưa chứng minh được nguyên nhân chênh số.

## Kết quả kiểm tra ngày 27/11/2026

**Nguyên nhân đã xác nhận: báo cáo dùng ngày UTC thay cho ngày Việt Nam.** Truy vấn `QC Internal Dataset` lọc, nhóm và sắp xếp bằng `DATE(e.occurred_at)`. Event lưu `occurred_at` theo UTC; ví dụ `2026-11-17 17:00:00` thuộc ngày 18/11 tại Việt Nam. Frappe đã lưu đúng ngày Việt Nam trong `e.server_date_key`; hệ thống đặt múi giờ `Asia/Ho_Chi_Minh`.

Với bộ lọc QC1, 16–22/11/2026, truy vấn hiện tại lấy ngày Việt Nam 17–23/11. Ngày 16/11 bị loại và ngày 23/11 được thêm vào:

| Ngày Việt Nam ở mép kỳ | Tổng kiểm | Tổng lỗi |
| --- | ---: | ---: |
| 16/11, bị loại nhầm | 15.413 | 7.903 |
| 23/11, được thêm nhầm | 27.074 | 9.756 |
| Tác động ròng | +11.661 | +1.853 |

Khi lọc trực tiếp `server_date_key` từ 16/11 đến 22/11, Frappe trả về 119.940 hàng kiểm và 54.586 lỗi, khớp Power BI và SQL nguồn **theo cả năm công ty**: Kim Thành 1 5.640/3.093; Kim Thành 2 35.508/14.651; Nam Quang 38.028/22.310; Quang Xuân 15.588/11.066; Việt Vương 3 25.176/3.466 (kiểm/lỗi). Công thức DAX và phép cộng số lượng có dấu không gây ra chênh lệch này.

Kiểm tra dữ liệu Pilot cho thấy 176.969 event QC1 và 85.651 event QC2 đều có `server_date_key`, trùng ngày `occurred_at` cộng 7 giờ; `event_uid` không trùng trong hai nhóm. Các event của kỳ so sánh được nạp ngày 26/11 với ID nguồn `legacy-qc-summary-row-*`, không phải ID dự phòng của Data Import. Chưa có bằng chứng phải sửa event gốc hay nạp lại dữ liệu.

## Script đã chạy

```sql
UPDATE `tabQC Inspection Event`
SET occurred_at = CAST(server_date_key AS DATETIME)
WHERE server_date_key IS NOT NULL
  AND DATE(occurred_at) <> server_date_key;
```

Lệnh chạy trong một giao dịch qua Pilot trên site `builder.localhost`. Nó sửa 262.613 trong 262.629 event hiện có; 16 event đã đúng ngày được giữ nguyên. Giờ của event sửa thành 00:00 UTC của ngày trong `server_date_key`. Sau cập nhật, không còn ngày lệch, `event_uid` trùng hoặc `Synced At` sớm hơn `Occurred At`.

API `QC Internal Dataset` cho QC1 ngày 16–22/11/2026 trả 119.940 kiểm, 54.586 lỗi; cả năm công ty khớp Power BI. QC2 cùng kỳ trả 75.727 kiểm, 16.922 lỗi. Bản sao giờ cũ của cả 262.629 event được giữ tại `/data/pilot-home/pilot/benches/ktg-8080/sites/builder.localhost/private/backups/qc-occurred-at-before-20261127T073704Z.tsv.gz` (SHA-256 `d90d6e3fa41b403670ee11afa025f6a4333795fef8d7dd410325518eebaa786e`).

## Điều kiện hoàn tất

- Với cùng khoảng ngày và filter, tổng kiểm, tổng lỗi, hàng đạt khớp chính xác với SQL/Power BI; các tỷ lệ được tính từ đúng tổng số.
- Không còn event dư, thiếu hoặc trùng chưa được giải thích; số tổng hợp theo công ty và ngày cộng lại đúng tổng chung.
- Bộ lọc QC1/QC2 và các chiều công ty, xưởng, chuyền, mã hàng không làm lệch phép tính.
- Dữ liệu Pilot đã được cập nhật và API báo cáo trả số đúng; không có thay đổi mã cần đẩy lên Git.

## Điểm cần theo dõi

Một lần làm mới toàn bộ từ snapshot nguồn có thể nạp lại giờ UTC cũ; event mới nhập sau script vẫn dùng quy tắc UTC ban đầu. Nếu cần duy trì ngày chuẩn cho các lần nhập sau, phải sửa luồng nhập hoặc chạy lại script. Sao lưu chuẩn của Pilot đã lỗi vì thư mục backup chứa các thư mục con; bản sao riêng của cột đã được kiểm tra đủ số dòng và checksum.
