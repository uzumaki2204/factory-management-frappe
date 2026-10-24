# Factory Management cho Frappe

Đây là app Frappe dùng chung cho dữ liệu nhà máy, thiết bị, QC và UQQC. Có hai bộ cài: cài Bench native mới trên máy Ubuntu sạch hoặc bổ sung app vào một stack Frappe Docker đã chạy.

## Cài vào stack Frappe Docker hiện có

Tải `factory-management-frappe-docker-v0.1.10.tar.gz` cùng `SHA256SUMS-docker-v0.1.10` lên máy đang chạy Frappe Docker, kiểm tra checksum, giải nén rồi chạy:

```bash
sha256sum -c SHA256SUMS-docker-v0.1.10
tar -xzf factory-management-frappe-docker-v0.1.10.tar.gz
cd factory-management-frappe-docker-v0.1.10
sudo ./install-docker.sh
```

Bộ cài đọc Compose project và image đang chạy từ metadata Docker, rồi kiểm tra Frappe 16.53.0, kiến trúc `linux/amd64` và `PULL_POLICY=never`. Trước khi triển khai, script yêu cầu xác nhận, sao lưu database cùng files của từng site, tạo image mới dựa trên image Frappe cục bộ và chỉ sửa `CUSTOM_TAG` trong `.env`. Sau đó nó tạo lại các dịch vụ backend, frontend, websocket, worker và scheduler; database cùng Redis không bị tạo lại. Script bật maintenance mode trong khi cài app, bật Server Scripts và chạy migrate. Các bản sao lưu và bản `.env` gốc được giữ trong thư mục `backups/factory-management-*` cạnh dự án Compose.

Không dùng gói Docker này cho máy chưa có stack Frappe Docker. Nếu máy có nhiều backend Compose, truyền tên container cần triển khai qua `FRAPPE_BACKEND_CONTAINER`. Gói không tự chạy trên máy Production khi được tạo; quản trị viên chủ động tải lên và chạy lệnh cài đặt.

## Cài mới trên Ubuntu 24.04 trở lên

Bộ cài native tạo một Bench production mới, cài Frappe 16.53.0 và app Factory Management, rồi tạo site dùng địa chỉ IPv4 của máy làm tên site. Bộ cài không nhập dữ liệu khách hàng, sản phẩm, chuyền, thiết bị, lịch sử kiểm tra hoặc token.

Tải gói `factory-management-frappe-v0.1.10.tar.gz` cùng `SHA256SUMS-native-v0.1.10`, kiểm tra SHA-256, giải nén rồi chạy:

```bash
sha256sum -c SHA256SUMS-native-v0.1.10
tar -xzf factory-management-frappe-v0.1.10.tar.gz
cd factory-management-frappe-v0.1.10
sudo ./install.sh
```

Bộ cài hỗ trợ Ubuntu 24.04 trở lên, kiến trúc x86_64, và cần Internet để lấy các phụ thuộc hệ điều hành. Nó tạo user Linux `frappe`, Bench tại `/opt/frappe-bench`, MariaDB 11.8, Redis, Nginx và Supervisor. Gói wkhtmltopdf được chọn theo phiên bản Ubuntu và xác minh SHA-256 trước khi cài: bản upstream Jammy trên Ubuntu 24.04, bản Noble tương thích cho Ubuntu 24.10–25.10, và bản Resolute cho Ubuntu 26.04 trở lên. Các bản Noble/Resolute được ghim từ [release 2026-05-06 của newinnovations/wkhtml-packaging](https://github.com/newinnovations/wkhtml-packaging/releases/tag/2026-05-06). Nhập mật khẩu cho tài khoản MariaDB cục bộ khi được hỏi; `bench new-site` sẽ hỏi lại mật khẩu đó và mật khẩu Administrator. Không dùng một Bench hoặc MariaDB đã có dữ liệu: bộ cài từ chối nếu thư mục Bench đích đã tồn tại.

Mở `http://<IP-LAN>/` để truy cập. Nếu firewall của máy đang bật, quản trị viên cần cho phép TCP/80 từ mạng LAN. Để cài từ repo riêng tư, clone tag `v0.1.10` trước rồi chạy cùng `sudo ./install.sh`; GitHub cần được cấu hình SSH deploy key trên máy cài.

## Phát hành

Tăng phiên bản trong `pyproject.toml`, `factory_management/__init__.py` và `release-manifest.json` đồng thời, sau đó chạy `./release.sh`. Lệnh tạo hai archive từ cùng một Git tag trong `dist/`: gói cài native và gói cài vào stack Docker hiện có. `SHA256SUMS` ghi cả hai checksum; các tệp `SHA256SUMS-native-<tag>` và `SHA256SUMS-docker-<tag>` dùng khi chỉ chuyển một archive. Dùng `./release.sh --publish` để đẩy cùng tag và nhánh `main` lên repo riêng `uzumaki2204/factory-management-frappe`; cần Git Credential Manager đã đăng nhập tài khoản có quyền ghi và tạo repo đó trước.

Manifest ghim Frappe 16.53.0 theo revision `e8d41dd0061a32ee781caefe5d0b0d2bb7c15362` ([bản phát hành chính thức](https://github.com/frappe/frappe/releases/tag/v16.53.0)). Các phụ thuộc runtime theo [hướng dẫn cài Frappe](https://docs.frappe.io/framework/user/en/installation). Bench cài app bằng `get-app` rồi `install-app`; migration dùng lệnh `bench --site <site> migrate` theo [hướng dẫn Bench](https://docs.frappe.io/framework/user/en/bench/reference/migrate).

## UQQC

UQQC dùng stylesheet mặc định `desk.bundle.css` và các thành phần chuẩn của Frappe Desk, không có CSS tùy biến riêng. Với trang đã tồn tại, chạy `bench --site <site> execute factory_management.uqqc.web_page.apply_desk_style` để áp dụng lại bố cục mặc định và xóa CSS của Web Page; lệnh này thay thế HTML hiện tại của riêng trang UQQC.

Trang tablet nằm tại `/uqqc`, có shortcut **UQQC** trong Desk. Module **UQQC**, package `factory_management.uqqc`, DocType **UQQC Inspection Event** và toàn bộ tài nguyên `/assets/factory_management/uqqc/` được đặt riêng. QC và UQQC dùng chung master **Factory Device** trong module **Factory Management**. Quyền từng trang ở **Factory Device Access** và token trình duyệt ở **Factory Device Client**; không ghi token vào sự kiện QC. Migration xóa **QC Device Client** và **UQQC Device Client** sau khi đối chiếu từng token với registry mới. Chỉ **System Manager** được sửa Web Page UQQC và quản lý thiết bị.

Danh mục lỗi của QC nằm trong bốn DocType **QC Defect Group**, **QC Defect**, **QC Defect Position Group**, **QC Defect Position**. UQQC dùng bốn DocType tương ứng mang tiền tố **UQQC**. Migration sao chép toàn bộ bản ghi QC hiện có sang UQQC với cùng `name` để giữ ID trong sự kiện lịch sử, mục yêu thích và hàng đợi offline; sau đó hai danh mục được quản lý độc lập. Import `QCDefect*` từ .NET chỉ cập nhật QC. **System Manager** và người có role **UQQC Catalog Manager** được quản lý danh mục UQQC trong Desk.

Chạy `bench --site <site> migrate` khi cài/nâng cấp app; patch `separate_uqqc_defects` sao chép danh mục và chuyển Link của sự kiện UQQC. Lệnh `bench --site <site> execute factory_management.uqqc.provision.ensure` chỉ tạo schema, Web Page, Server Scripts và hợp đồng còn thiếu; không chạy patch sao chép dữ liệu. Site cần bật Server Scripts như API QC hiện tại. Provision không ghi đè nội dung đã sửa trong Desk.

| Phương thức | API Method | Chức năng |
| --- | --- | --- |
| GET | `/api/method/uqqc-bootstrap` | Master data dùng chung, danh mục lỗi UQQC và đồng hồ site; nhận `deviceId` trong query |
| POST | `/api/method/uqqc-device-register` | Ghép token của trình duyệt với Device ID đã có |
| POST | `/api/method/uqqc-device-check` | Kiểm tra trạng thái và ghép nối |
| POST | `/api/method/uqqc-inspections-sync` | Gửi `events`, `passEvents`, `reworkEvents`; tối đa 500 sự kiện |
| POST | `/api/method/uqqc-inspections-snapshot` | Tổng hợp một lựa chọn trong ngày |
| POST | `/api/method/uqqc-inspections-detail-snapshot` | Toàn bộ lựa chọn của thiết bị trong ngày |

Các POST nhận JSON có `deviceId`; snapshot cần thêm `lineId`, `productId`, `colorId`, `sizeId`, `marketId`. Phản hồi dùng envelope Frappe `message`. `defectId` và `defectPositionId` trong API đồng bộ phải thuộc danh mục UQQC đang hoạt động. URL, header token, tên trường và ID trong payload không đổi. Server Scripts gọi các dịch vụ kiểm tra dữ liệu trong package UQQC; sửa orchestration ở **Server Script**, sửa nghiệp vụ dùng chung trong package.

Tablet tự sinh token ngẫu nhiên cho từng Device ID, lưu riêng trong trình duyệt và gửi qua `X-UQQC-Token`; không chứa API key/secret của User. Thiết bị phải được duyệt, hoạt động, gán công ty, có quyền UQQC đang bật và token UQQC hợp lệ. Đăng ký tạo quyền UQQC đang tắt nếu thiết bị chưa có quyền; quản trị viên bật quyền tại **Factory Device Access**. Thu hồi token tại **Factory Device Client** với `service_key=uqqc`; token QC không được chấp nhận bởi UQQC.

Trong **API Management**, chọn Service **UQQC API**. Bootstrap và hai API snapshot còn hỗ trợ User Frappe/API key có role trong **Allowed Roles**, mặc định là `UQQC API Reader`. Việc gán role cho User do quản trị viên thực hiện. Role này không cấp quyền ghi sự kiện hoặc đọc DocType trực tiếp. Xóa allowlist chặn truy cập theo User; tablet vẫn dùng token thiết bị. Tắt Endpoint hoặc Service chặn mọi cách gọi API tương ứng. Administrator/System Manager cũng phải khớp allowlist khi đọc bằng danh tính User.

Resource ngôn ngữ dùng chung frontend/backend là `factory_management/public/uqqc/i18n.json` (Việt/Anh). Trang mặc định tiếng Việt; mở `/uqqc?lang=en` để dùng tiếng Anh. Dữ liệu thời gian lưu UTC, ngày tổng hợp theo múi giờ Frappe site. Hai lỗi trên cùng một `defectPieceId` tính là hai lỗi nhưng một sản phẩm lỗi. Gửi lại cùng mã sự kiện được xác nhận mà không ghi thêm; dùng lại mã với nội dung khác bị từ chối và giữ hàng đợi trên tablet.

Khi MariaDB báo deadlock hoặc xung đột snapshot giữa các yêu cầu đồng thời, API sync trả HTTP 409 với `exc_type=UQQCSyncRetryError`; Frappe rollback toàn bộ yêu cầu. Tablet giữ nguyên hàng đợi và tự thử lại, không coi đây là mất kết nối. API consumer khác cần gửi lại cùng mã sự kiện sau khi yêu cầu đang chạy hoàn tất.

Chạy kiểm tra JavaScript bằng `node --test integrations/frappe/factory-management/tests/uqqc-client.test.js` từ workspace. Kiểm tra tích hợp sáu Server Scripts bằng `bench --site <site> execute factory_management.uqqc.verification.run`; dữ liệu thử và thay đổi phân quyền được rollback trong `finally`. Nên chạy khi site không đang thay đổi master data. HTTPS cần thiết để trình duyệt cho phép camera và mở lại PWA khi mất mạng; địa chỉ HTTP nội bộ vẫn dùng nhập mã thiết bị và hàng đợi khi trang đang mở.

## Tài liệu API

Từ màn hình `/desk`, chọn **QC** để mở trang QC trong tab mới hoặc **API Docs** để mở tài liệu và quản lý API trong Desk. Biểu tượng API Docs chỉ hiển thị cho System Manager.

- Trong Desk, mở module **API Management** → **API Documentation**.
- **API Documentation Service** quản lý từng dịch vụ, phiên bản, URL máy chủ và URL OpenAPI có sẵn.
- **API Documentation Endpoint** quản lý đường dẫn, phương thức, tham số, schema phản hồi và bảng **Allowed Roles** của từng API báo cáo QC.
- Catalog QC mô tả `/api/method/qc-inspection-summary`, `/api/method/factory_management.api.report_summary` và `/api/method/factory_management.api.report_detail`. Swagger UI cho phép xem schema, role được phép, gọi thử API và tải tệp OpenAPI JSON.
- Trang tài liệu và API xuất hợp đồng chỉ dành cho vai trò **System Manager**. Chỉnh sửa hợp đồng cập nhật tài liệu; mã xử lý của API được sửa tại Server Script hoặc mã app tương ứng.

Để cấp quyền đọc báo cáo, mở **User → Roles** và gán `QC Report Reader` cho User cần gọi API. Sau đó mở **API Management → API Documentation Endpoint → Allowed Roles** để chọn role được phép ở từng API. Ba API báo cáo nhận `QC Report Reader` khi nâng cấp lần đầu; thay đổi trong Desk được giữ lại sau các lần nâng cấp tiếp theo. Một User có nhiều role chỉ cần khớp một role được phép; System Manager và Administrator cũng phải có role khớp. API key và API secret dùng quyền của User sở hữu chúng. Các API tablet tiếp tục xác thực bằng `X-QC-Token`.

Sau khi cài app, chạy `bench --site <site> migrate`. API `qc-inspection-summary` là Server Script; để tạo nó trên site mới, bật `server_script_enabled` và chạy `bench --site <site> execute factory_management.provision.ensure_qc_inspection_summary`.

## Trang QC trong Desk

Sau khi migrate, vào **Website → Web Page**, mở bản ghi **QC** (route `/qc`) để sửa HTML và CSS. Trang được tạo một lần; các lần migrate tiếp theo không ghi đè thay đổi trong Desk. Chỉ **System Manager** được sửa bản ghi QC. Trang `/qc` vẫn mở được cho tablet chưa đăng nhập; đăng ký thiết bị và dữ liệu QC tiếp tục dùng API của app.

Khi phân phối QC cho site khác, xuất bản Web Page đã duyệt từ Desk rồi nhập trên site đích. Nếu site đích chưa có Web Page route `qc`, lần migrate đầu sẽ tạo bản mặc định đi kèm app. JavaScript QC, manifest và service worker vẫn được phát hành cùng mã app. Địa chỉ HTTP trong mạng nội bộ không cho service worker hoạt động trên phần lớn trình duyệt; dùng HTTPS nếu cần mở lại trang khi mất mạng.

Khi thêm microservice khác, có thể nhập URL OpenAPI của dịch vụ vào bản ghi Service. Trình duyệt cần được phép đọc URL đó qua CORS nếu nó nằm ở miền khác Frappe.
