# Factory Management cho Frappe

Đây là app Frappe dùng chung cho dữ liệu nhà máy, thiết bị, QC và UQQC. Phương thức cài đặt chính là lấy app từ [repo GitHub công khai](https://github.com/uzumaki2204/factory-management-frappe) bằng Bench, giống cách cài ERPNext. App này được cài vào Bench và site Frappe đã có sẵn; nó không tự cài hệ điều hành, Bench hoặc tạo site.

## Cài vào Bench đã có sẵn

Đảm bảo Bench đang chạy Frappe 16.53.0 trở lên trong nhánh v16, sau đó chạy dưới tài khoản sở hữu Bench:

```bash
cd ~/frappe-bench
bench get-app --branch version-16 factory_management https://github.com/uzumaki2204/factory-management-frappe.git
bench --site <ten-site> set-config server_script_enabled 1
bench --site <ten-site> install-app factory_management
bench --site <ten-site> migrate
bench --site <ten-site> execute factory_management.provision.ensure_qc_inspection_summary
bench build --app factory_management
bench restart
```

Tên app Frappe là `factory_management`; vì vậy lệnh `get-app` ghi rõ tên này trước URL repo. Repo công khai nên máy cài không cần SSH deploy key để tải mã nguồn. Khi muốn ghim đúng một bản phát hành, thay `version-16` bằng tag, ví dụ `v0.1.20`.

Trong Pilot, chọn repo `uzumaki2204/factory-management-frappe` và nhánh `version-16`. Giá trị `project.name` trong `pyproject.toml` phải là `factory_management` để Pilot tìm thấy `factory_management/hooks.py`. Nếu app đã có trên bench, dùng chức năng cập nhật app thay vì import lại.

Khi nâng cấp, tạo bản sao lưu trước, lấy mã mới từ `version-16`, rồi chạy migrate, build và restart. App tự chạy `after_install` và `after_migrate` để tạo schema, trang QC/UQQC và API UQQC. Lệnh `ensure_qc_inspection_summary` ở trên tạo Server Script QC còn lại. Server Scripts phải được bật trước khi cài app.

## Đồng bộ cấu hình DocType giữa các máy

Metadata DocType được quản lý bằng snapshot JSON trong `factory_management/doctype_metadata/`. Snapshot gồm fields, Naming, Settings, Permissions, Actions, Links, States, Custom Fields, Property Setters và các Role được tham chiếu; tab Connections của Frappe được tạo từ các Link/field này. Snapshot không chứa tài khoản người dùng hoặc phân công Role cho người dùng. Khi có snapshot, `bench migrate` áp dụng metadata đó cho các DocType do app quản lý. Bản ghi master, sự kiện và dữ liệu người dùng vẫn được giữ.

Để đưa cấu hình đang có trên máy nguồn vào app, trước hết cài bản app có hỗ trợ xuất metadata lên máy đó và chạy migrate. Lần nâng cấp đầu giữ nguyên metadata hiện tại của DocType đã tồn tại. Sau đó chạy:

```bash
bench --site <ten-site> execute factory_management.install.export_doctype_metadata
```

Lệnh tạo JSON trong `apps/factory_management/factory_management/doctype_metadata/`. Lấy các file này về repo, commit và phát hành app. Cài/nâng cấp bản phát hành đó trên máy đích rồi chạy `bench --site <ten-site> migrate` để áp dụng cấu hình nguồn. Các snapshot là nguồn chuẩn sau khi đã xuất; chỉnh sửa DocType trực tiếp trên máy đích cần được xuất về repo nếu muốn giữ qua lần nâng cấp tiếp theo.

Nếu không có snapshot cho một DocType, app giữ định nghĩa đang có trên site; với DocType mới, app tạo theo cấu hình mặc định trong mã nguồn.

Trên máy mới, cần cài Bench/Frappe và tạo site trước khi chạy các lệnh này. Các bộ cài native và Docker bên dưới vẫn có thể dùng như lựa chọn dựng môi trường hoặc triển khai stack Docker; chúng là bộ cài hạ tầng bổ sung, không phải cách cài app Bench thông thường.

## Bộ cài phụ trợ cho stack Frappe Docker hiện có

Tải `factory-management-frappe-docker-v0.1.20.tar.gz` cùng `SHA256SUMS-docker-v0.1.20` lên máy đang chạy Frappe Docker, kiểm tra checksum, giải nén rồi chạy:

```bash
sha256sum -c SHA256SUMS-docker-v0.1.20
tar -xzf factory-management-frappe-docker-v0.1.20.tar.gz
cd factory-management-frappe-docker-v0.1.20
sudo ./install-docker.sh
```

Bộ cài đọc Compose project và image đang chạy từ metadata Docker, rồi kiểm tra Frappe 16.53.0, kiến trúc `linux/amd64` và `PULL_POLICY=never` hoặc `missing`. Cả hai chính sách đều dùng image đã có trên máy; Compose chỉ kéo image với `missing` khi image chưa có trong cache. Trước khi triển khai, script yêu cầu xác nhận, sao lưu database cùng files của từng site, tạo image mới dựa trên image Frappe cục bộ và chỉ sửa `CUSTOM_TAG` trong `.env`. Sau đó nó tạo lại các dịch vụ backend, frontend, websocket, worker và scheduler; database cùng Redis không bị tạo lại. Script bật maintenance mode trong khi cài app, bật Server Scripts và chạy migrate. Các bản sao lưu và bản `.env` gốc được giữ trong thư mục `backups/factory-management-*` cạnh dự án Compose.

Không dùng gói Docker này cho máy chưa có stack Frappe Docker. Nếu máy có nhiều backend Compose, truyền tên container cần triển khai qua `FRAPPE_BACKEND_CONTAINER`. Gói không tự chạy trên máy Production khi được tạo; quản trị viên chủ động tải lên và chạy lệnh cài đặt.

## Bộ cài phụ trợ tạo Bench mới trên Ubuntu 24.04 trở lên

Bộ cài native tạo một Bench production mới, cài Frappe 16.53.0 và app Factory Management, rồi tạo site dùng địa chỉ IPv4 của máy làm tên site. Bộ cài không nhập dữ liệu khách hàng, sản phẩm, chuyền, thiết bị, lịch sử kiểm tra hoặc token.

Tải gói `factory-management-frappe-v0.1.20.tar.gz` cùng `SHA256SUMS-native-v0.1.20`, kiểm tra SHA-256, giải nén rồi chạy:

```bash
sha256sum -c SHA256SUMS-native-v0.1.20
tar -xzf factory-management-frappe-v0.1.20.tar.gz
cd factory-management-frappe-v0.1.20
sudo ./install.sh
```

Bộ cài hỗ trợ Ubuntu 24.04 trở lên, kiến trúc x86_64, và cần Internet để lấy các phụ thuộc hệ điều hành. Nó tạo user Linux `frappe`, Bench tại `/opt/frappe-bench`, MariaDB 11.8, Redis, Nginx và Supervisor. Gói wkhtmltopdf được chọn theo phiên bản Ubuntu và xác minh SHA-256 trước khi cài: bản upstream Jammy trên Ubuntu 24.04, bản Noble tương thích cho Ubuntu 24.10–25.10, và bản Resolute cho Ubuntu 26.04 trở lên. Các bản Noble/Resolute được ghim từ [release 2026-05-06 của newinnovations/wkhtml-packaging](https://github.com/newinnovations/wkhtml-packaging/releases/tag/2026-05-06). Nhập mật khẩu cho tài khoản MariaDB cục bộ khi được hỏi; `bench new-site` sẽ hỏi lại mật khẩu đó và mật khẩu Administrator. Không dùng một Bench hoặc MariaDB đã có dữ liệu: bộ cài từ chối nếu thư mục Bench đích đã tồn tại.

Mở `http://<IP-LAN>/` để truy cập. Nếu firewall của máy đang bật, quản trị viên cần cho phép TCP/80 từ mạng LAN. Repo hiện công khai; bộ cài này tải mã nguồn mà không cần SSH deploy key.

## Phát hành

Tăng phiên bản trong `pyproject.toml`, `factory_management/__init__.py` và `release-manifest.json` đồng thời. Sau đó chạy `./release.sh --publish`. Lệnh phát hành cùng commit thành tag `v<version>`, nhánh `main` và nhánh tương thích Frappe đã khai báo trong manifest (hiện là `version-16`) lên repo công khai `uzumaki2204/factory-management-frappe`. Máy cài chỉ cần quyền đọc repo; người phát hành vẫn cần quyền ghi GitHub.

Script cũng tạo hai archive phụ trợ từ cùng tag trong `dist/`: bộ cài native và bộ triển khai stack Docker. `SHA256SUMS` ghi cả hai checksum; các tệp `SHA256SUMS-native-<tag>` và `SHA256SUMS-docker-<tag>` dùng khi chuyển riêng từng archive. Luồng Bench qua Git là phương thức cài app được khuyến nghị.

Manifest ghi Frappe 16.53.0 làm phiên bản chuẩn kiểm tra theo revision `e8d41dd0061a32ee781caefe5d0b0d2bb7c15362` ([bản phát hành chính thức](https://github.com/frappe/frappe/releases/tag/v16.53.0)). Metadata Bench trong `pyproject.toml` khai báo app tương thích Frappe `>=16.53.0,<17.0.0`. Các phụ thuộc runtime theo [hướng dẫn cài Frappe](https://docs.frappe.io/framework/user/en/installation). Bench tải mã bằng `get-app`, cài app vào site bằng `install-app` và cập nhật schema bằng `migrate` theo [tài liệu Bench](https://docs.frappe.io/framework/user/en/bench/bench-commands).

## Nhập PO từ SPL

Từ bản `0.1.45`, trang Desk `/desk/factory-management/spl-po-import` trong module **Factory Management** cho System Manager kiểm tra kết nối, lấy workbook SPL, xem trước theo trang, chọn dòng và xác nhận nhập. Bản `0.1.46` thêm biểu tượng **Import SPL** trên màn hình Desktop của System Manager. Bản `0.1.47` sửa preview khi thiếu master: cảnh báo sẽ tạo mới Product, Product Color, ProductSize và Production Season hiển thị đúng, sau đó importer tạo master khi xác nhận nhập. Bản `0.1.48` cho bảng xem trước dùng hết chiều rộng Desk và hiển thị tiến độ cùng số PO/dòng đã nhập, PO lỗi ngay cạnh nút nhập khi tác vụ hoàn tất. Bản `0.1.49` chuẩn hóa đường dẫn snapshot để nút nhập chấp nhận bản xem trước được lưu ở dạng tương đối hoặc tuyệt đối. Có thể tải lên workbook `.xls` hoặc `.xlsx` riêng tư thay cho tải trực tiếp. Trang dùng các DocType **SPL Purchase Order**, **SPL Purchase Order Item**, **SPL Import Settings** và **SPL Import Run**; `bench migrate` tạo schema qua patch `add_spl_po_import` và đăng ký lịch.

Trong **SPL Import Settings**, chọn Customer, nhập tài khoản/mật khẩu SPL và chọn chứng chỉ PFX/P12 đã tải lên dạng **Private File** cùng mật khẩu chứng chỉ. URL mặc định là `https://spl.fastretailing.com`; chỉ HTTPS và host trong `spl_po_allowed_hosts` của site config được phép. Mặc định chỉ cho phép `spl.fastretailing.com`. Không lưu password hoặc token trong workbook, snapshot và lịch sử nhập. Các bộ lọc SPL mặc định tương ứng project .NET; có thể điều chỉnh trong Settings. Bản `0.1.50` thêm lựa chọn Answer Status và Document Status theo mã và tên; bản `0.1.51` sửa tải client selector trên Desk; bản `0.1.52` dàn phần cài đặt thành hai cột.

Preview có hiệu lực 15 phút và nằm trong `sites/<site>/private/files/spl_po/`. Nút nhập xác nhận đúng snapshot đã xem; mỗi PO/revision là một giao dịch và nhập lại sẽ cập nhật các dòng của PO đó. Chỉ chọn một PO nếu đã chọn đủ tất cả dòng của PO. Trong **SPL Import Settings**, chọn Answer Status và Document Status bằng danh sách checkbox hiển thị cả mã lẫn tên. Master thiếu được hiển thị trong preview và tự tạo khi nhập; Product tạo inactive như importer .NET. Kiểm tra bản ghi **SPL Import Run** để xem PO thất bại và xử lý dữ liệu trước khi nhập lại.

Desk gọi các method System Manager `factory_management.spl_po.api.test_connection`, `start_preview`, `get_run`, `get_preview_page` và `start_import` qua `/api/method/`. `start_preview` nhận tùy chọn `file_url` của Private File; `get_run` trả `run_name`, trạng thái và `snapshot_token` khi preview sẵn sàng; `get_preview_page` nhận `run_name`, `token`, `page`; `start_import` nhận `run_name`, `token`, `selected_rows="all"` và `excluded_rows` (JSON array). Các method tạo tác vụ chỉ nhận POST và đưa công việc vào queue `long`.

Lịch mặc định tắt. Khi bật, nhập các giờ địa phương dạng `08:00,13:00` trong **Schedule Times** và múi giờ IANA (mặc định `Asia/Ho_Chi_Minh`); Frappe scheduler kiểm tra mỗi phút và tự tải/nhập. Cần worker queue `long` hoạt động. Trước khi cập nhật Pilot, chạy `bench --site <site> backup --with-files`; sau cập nhật app, chạy migrate nếu Pilot chưa thực hiện, kiểm tra Settings, preview bằng workbook đã làm sạch rồi mới nhập dữ liệu thật.

Kiểm thử parser/gateway không cần site (cài thêm extra `.[test]` để tạo fixture `.xls`): `python -m unittest discover -s tests -p 'test_spl_po*.py' -v`. Kiểm thử upsert trên site thử: `bench --site <site-thu> run-tests --app factory_management --module factory_management.spl_po.test_spl_po_frappe`.

## Generation dữ liệu sau khi làm mới QC

`GET /api/method/factory_management.api.data_epoch` trả `{generation, resetAtUtc}` trong `message`. Trước lần làm mới, `generation` rỗng. Sau lần làm mới, các lệnh ghi/đăng ký/kiểm tra thiết bị QC và UQQC cần header `X-Factory-Data-Epoch` bằng generation hiện tại; request cũ bị từ chối. Client QC/UQQC đọc generation trước khi đồng bộ và xóa queue, cache cũ khi generation đổi. DocType `Factory Data Epoch` chỉ lưu generation của site. Luồng làm mới do MigrationFrappe chạy cục bộ bằng Bench trong Docker; không có API HTTP để xóa dữ liệu.

Lần làm mới lấy master, thiết bị và `QCInspections` từ SQL Server .NET, dựng lại danh mục lỗi UQQC từ QC và để trống sự kiện UQQC. Cần backup và kiểm tra xung đột Link với app khác trước khi chạy. Không thay đổi dữ liệu QCBrother trong SQL Server.

## UQQC

Từ bản `0.1.54`, các trường Link trong **UQQC Inspection Event** hiển thị **Defect Position** và **Defect** theo `code`, **Device** theo `device_name`. Metadata `title_field` và `show_title_field_in_link` áp dụng nhãn này cho form, danh sách và ô chọn Link. Patch `set_uqqc_link_titles` cập nhật site đã cài và xóa cache metadata khi migrate; khóa bản ghi và các liên kết dữ liệu được giữ nguyên.

### ID Factory Device

Factory Device dùng khóa chính Frappe `name` với giá trị UUID. Hook `before_naming` cấp UUID cho thiết bị mới và giữ ID UUID đã được cung cấp; DocType dùng quy tắc `prompt` để giữ kiểu cột khóa chính hiện có khi nâng cấp site có dữ liệu. Khi nâng cấp, migration kiểm tra mọi `device_id` cũ bằng `name`, giữ nguyên ID hiện có và Link từ QC/UQQC, rồi xóa `device_id`, `device_uid` và DocType `Factory Device Client`. Thiết bị không còn token; API tablet dùng tham số `id`, vẫn nhận tạm `device_id`/`deviceId` và trả alias `device_id` cho client cũ. Trước khi chạy migration trên site có dữ liệu, sao lưu database cùng public/private files bằng `bench --site <site> backup --with-files`, sau đó chạy `bench --site <site> migrate` và kiểm tra lại các liên kết thiết bị. Nếu hai ID cũ không khớp, migration dừng trước khi xóa cột.

UQQC dùng stylesheet mặc định `desk.bundle.css` và các thành phần chuẩn của Frappe Desk, không có CSS tùy biến riêng. Với trang đã tồn tại, chạy `bench --site <site> execute factory_management.uqqc.web_page.apply_desk_style` để áp dụng lại bố cục mặc định và xóa CSS của Web Page; lệnh này thay thế HTML hiện tại của riêng trang UQQC.

Trang tablet nằm tại `/uqqc`, có shortcut **UQQC** trong Desk. Module **UQQC**, package `factory_management.uqqc`, DocType **UQQC Inspection Event** và toàn bộ tài nguyên `/assets/factory_management/uqqc/` được đặt riêng. QC và UQQC dùng chung **Factory Device** trong module **Factory Management**. ID bản ghi Frappe (`name`) là định danh duy nhất; hai trang kiểm tra ID, trạng thái Approved và Active. UQQC còn yêu cầu thiết bị được gán Công ty. Migration xóa **Factory Device Client** và token cũ. Chỉ **System Manager** được sửa Web Page UQQC và quản lý thiết bị.

Danh mục lỗi QC dùng hai DocType **QC Defect** và **QC Defect Position**. Mỗi DocType lưu cả bản ghi nhóm và bản ghi lỗi/vị trí, phân biệt bằng `record_type` và liên kết nhóm tự tham chiếu. UQQC dùng hai DocType độc lập tương ứng mang tiền tố **UQQC**. Migration chuyển các nhóm cũ sang DocType gộp, giữ nguyên tên bản ghi được liên kết trong sự kiện, mục yêu thích và ánh xạ dữ liệu, rồi xóa DocType nhóm cũ. Dữ liệu QC và UQQC tiếp tục được quản lý độc lập; API tablet giữ nguyên URL và payload. Import `QCDefect*` từ .NET chỉ cập nhật QC. **System Manager** và người có role **UQQC Catalog Manager** được quản lý danh mục UQQC trong Desk.

Chạy `bench --site <site> migrate` khi cài/nâng cấp app; patch `separate_uqqc_defects` sao chép danh mục và chuyển Link của sự kiện UQQC. Lệnh `bench --site <site> execute factory_management.uqqc.provision.ensure` chỉ tạo schema, Web Page, Server Scripts và hợp đồng còn thiếu; không chạy patch sao chép dữ liệu. Site cần bật Server Scripts như API QC hiện tại. Provision không ghi đè nội dung đã sửa trong Desk.

| Phương thức | API Method | Chức năng |
| --- | --- | --- |
| GET | `/api/method/uqqc-bootstrap` | Master data dùng chung, danh mục lỗi UQQC và đồng hồ site; nhận `id` trong query |
| POST | `/api/method/uqqc-device-register` | Kiểm tra ID thiết bị đã có |
| POST | `/api/method/uqqc-device-check` | Kiểm tra trạng thái thiết bị |
| POST | `/api/method/uqqc-inspections-sync` | Gửi `events`, `passEvents`, `reworkEvents`; tối đa 500 sự kiện |
| POST | `/api/method/uqqc-inspections-snapshot` | Tổng hợp một lựa chọn trong ngày |
| POST | `/api/method/uqqc-inspections-detail-snapshot` | Toàn bộ lựa chọn của thiết bị trong ngày |

Các POST nhận JSON có `id`; snapshot cần thêm `lineId`, `productId`, `colorId`, `sizeId`, `marketId`. Phản hồi dùng envelope Frappe `message`. `defectId` và `defectPositionId` trong API đồng bộ phải thuộc danh mục UQQC đang hoạt động. Giai đoạn tương thích còn nhận `deviceId` và `device_id`; phản hồi có alias `device_id`. Server Scripts gọi các dịch vụ kiểm tra dữ liệu trong package UQQC.

Tablet gửi `id` của Factory Device, không gửi token. Thiết bị phải được duyệt, đang hoạt động và gán công ty. Người biết ID của một thiết bị đủ điều kiện có thể gọi API tablet QC/UQQC tương ứng; ID không phải bí mật.

Trong **API Management**, chọn Service **UQQC API**. Tắt Endpoint hoặc Service sẽ chặn mọi cách gọi API tương ứng. Các endpoint tablet dùng điều kiện trạng thái thiết bị, không dùng Allowed Roles.

Resource ngôn ngữ dùng chung frontend/backend là `factory_management/public/uqqc/i18n.json` (Việt/Anh). Trang mặc định tiếng Việt; mở `/uqqc?lang=en` để dùng tiếng Anh. Dữ liệu thời gian lưu UTC, ngày tổng hợp theo múi giờ Frappe site. Hai lỗi trên cùng một `defectPieceId` tính là hai lỗi nhưng một sản phẩm lỗi. Gửi lại cùng mã sự kiện được xác nhận mà không ghi thêm; dùng lại mã với nội dung khác bị từ chối và giữ hàng đợi trên tablet.

Khi MariaDB báo deadlock hoặc xung đột snapshot giữa các yêu cầu đồng thời, API sync trả HTTP 409 với `exc_type=UQQCSyncRetryError`; Frappe rollback toàn bộ yêu cầu. Tablet giữ nguyên hàng đợi và tự thử lại, không coi đây là mất kết nối. API consumer khác cần gửi lại cùng mã sự kiện sau khi yêu cầu đang chạy hoàn tất.

Chạy kiểm tra JavaScript bằng `node --test integrations/frappe/factory-management/tests/uqqc-client.test.js` từ workspace. Kiểm tra tích hợp sáu Server Scripts bằng `bench --site <site> execute factory_management.uqqc.verification.run`; dữ liệu thử và thay đổi phân quyền được rollback trong `finally`. Nên chạy khi site không đang thay đổi master data. HTTPS cần thiết để trình duyệt cho phép camera và mở lại PWA khi mất mạng; địa chỉ HTTP nội bộ vẫn dùng nhập mã thiết bị và hàng đợi khi trang đang mở.

## Làm gọn sự kiện QC/UQQC trên site đã có dữ liệu

Bản này giữ `Local Event ID` cho đồng bộ offline. QC bỏ `Event Key`, `Entity Type`, `Entity ID` và `Payload`; UQQC bỏ `Fingerprint`, `Event UID` và cột lưu `Server Date Key`. API UQQC vẫn trả `serverDateKey` tính theo múi giờ site. Trước khi chạy lệnh dưới đây, sao lưu **database và public/private files** của từng site, bật maintenance và cập nhật app trên site đó. Lệnh xóa toàn bộ bản ghi trong hai DocType sự kiện, đổi data epoch để hàng đợi tablet cũ không gửi lại, và chỉ xóa bảy cột được nêu. Các danh mục và thiết bị không bị xóa. Lệnh được gọi thủ công để nâng cấp app trên site khác không tự xóa lịch sử.

```bash
bench --site <site> migrate
bench --site <site> execute factory_management.patches.retire_inspection_event_fields.execute
bench --site <site> clear-cache
```

Sau đó kiểm tra hai bảng sự kiện trống và mở QC/UQQC trên tablet để đăng ký lại generation. Nếu bước thực thi lỗi, giữ maintenance và khôi phục bản backup trước khi mở site.

## Chuyền trong KTG Master Data

`Production Line`, `Line Group` và `Line Group Assignment` thuộc module **KTG Master Data**. Tên bản ghi **Production Line** dùng `line_code`; khi nâng cấp, Frappe đổi tên bản ghi hiện có và cập nhật các Link tham chiếu. `line_code` phải có giá trị, không có khoảng trắng thừa, không vượt quá 140 ký tự và duy nhất không phân biệt hoa thường trên toàn site. Migration dừng trước khi đổi tên nếu phát hiện mã không hợp lệ hoặc trùng. Bản ghi **Line Group** mới dùng `group_code` làm tên; các tên bản ghi hiện có được giữ để bảo toàn Link.

DocType `Size` được đổi thành **ProductSize**, thuộc **KTG Master Data** và dùng `size_label` làm tên cho bản ghi mới. Migration Frappe đổi tên DocType/bảng và cập nhật các trường Link, nhưng giữ nguyên tên các bản ghi size hiện có để bảo toàn dữ liệu tham chiếu. Nhãn size cần có giá trị, không trùng và không vượt quá 140 ký tự.

`Factory`, `Product Color` và `Production Season` cũng thuộc **KTG Master Data**, lần lượt dùng `factory_code`, `color_code` và `season_code` để đặt tên bản ghi mới. **QC Defect** vẫn thuộc **Quality Control** và dùng `code`. Thay đổi quy tắc không đổi tên các bản ghi hiện có để giữ nguyên Link; mã dùng để tạo tên mới cần duy nhất trong DocType.

`Product Variant` dùng trường `product_color` (nhãn **Product Color**) Link tới danh mục `Product Color`. Khi nâng cấp, app chuyển giá trị `qc_color` và các giá trị `color` khớp chính xác tên bản ghi `Product Color` sang trường mới, sau đó gỡ hai trường cũ. Migrate dừng trước khi gỡ trường nếu có mã màu không khớp hoặc các giá trị mâu thuẫn. Tích hợp dùng trực tiếp Frappe Resource API cần đổi fieldname `qc_color` thành `product_color`; payload QC/UQQC tiếp tục dùng `colorId`, `color_id` và `colors`.

## Tài liệu API

Từ màn hình `/desk`, chọn **QC** để mở trang QC trong tab mới hoặc **API Docs** để mở tài liệu và quản lý API trong Desk. Biểu tượng API Docs chỉ hiển thị cho System Manager.

- Trong Desk, mở module **API Management** → **API Documentation**.
- **API Documentation Service** quản lý từng dịch vụ, phiên bản, URL máy chủ và URL OpenAPI có sẵn.
- **API Documentation Endpoint** quản lý đường dẫn, phương thức, tham số, schema phản hồi và bảng **Allowed Roles** của từng API báo cáo QC.
- Catalog QC mô tả `/api/method/qc-inspection-summary`, `/api/method/factory_management.api.report_summary` và `/api/method/factory_management.api.report_detail`. Swagger UI cho phép xem schema, role được phép, gọi thử API và tải tệp OpenAPI JSON.
- Trang tài liệu và API xuất hợp đồng chỉ dành cho vai trò **System Manager**. Chỉnh sửa hợp đồng cập nhật tài liệu; mã xử lý của API được sửa tại Server Script hoặc mã app tương ứng.

Để cấp quyền đọc báo cáo, mở **User → Roles** và gán `QC Report Reader` cho User cần gọi API. Sau đó mở **API Management → API Documentation Endpoint → Allowed Roles** để chọn role được phép ở từng API. Các API báo cáo nhận `QC Report Reader` khi được tạo lần đầu; thay đổi trong Desk được giữ lại sau các lần nâng cấp tiếp theo. Một User có nhiều role chỉ cần khớp một role được phép; System Manager và Administrator cũng phải có role khớp. API key và API secret dùng quyền của User sở hữu chúng. Các API tablet dùng `id` của Factory Device.

### Báo cáo QCBrother từ SQL Server

Từ bản `0.1.53`, service **QC API** có hai GET method, trả danh sách dưới `message` của Frappe:

- `/api/method/factory_management.qcbrother_reports.inspection_summary`: query bắt buộc `occurredOnFrom`, `occurredOnTo`, tối đa 7 ngày tính cả hai đầu; filter tùy chọn `companyId`, `companyCode`, `qc`, `sampleCode`, `eventNo`.
- `/api/method/factory_management.qcbrother_reports.inspection_aggregate`: cùng query ngày và filter công ty/QC/mã hàng, tối đa 31 ngày; không nhận filter `eventNo`.

Hai method chỉ chạy `SELECT` có tham số trên SQL Server gốc, không dùng dữ liệu `QC Inspection Event` trong MariaDB. Chúng đọc `QCBrotherInspectionEvents`, `QCBrotherInspectionQuantityEvents`, `QCBrother`, master và PO của cùng database. Dữ liệu legacy tính một đơn vị mỗi record; công ty chỉ được resolve theo chuyền. Aggregate giữ total toàn bộ lịch sử theo QC + công ty + mã hàng, trong khi từng dòng ngày vẫn phân biệt serial và biến thể. `plannedQuantity` dùng revision PO mới nhất có trạng thái chứng từ `New` hoặc `Change`.

Cấu hình riêng cho site bằng khóa `qcbrother_sqlserver` trong `site_config.json` (không commit tệp này). Dùng thông tin kết nối thực tế thay cho các placeholder sau:

```json
{
  "qcbrother_sqlserver": {
    "host": "<sql-server-host>",
    "port": 1433,
    "database": "<database>",
    "user": "<sql-login>",
    "password": "<sql-password>",
    "time_zone": "Asia/Ho_Chi_Minh",
    "connect_timeout": 10,
    "query_timeout": 60,
    "trust_server_certificate": false
  }
}
```

`time_zone` phải khớp timezone local của API .NET nguồn; mặc định dùng System Settings của site. Sự kiện mới lưu UTC, còn `QCBrother.OccurredOn` là thời gian local. `occurredOn` trả đầu ngày ISO 8601 kèm UTC offset ở cả hai API. Kết nối luôn mã hóa; chỉ bật `trust_server_certificate` khi cấu hình nguồn dùng chứng chỉ nội bộ được tin cậy theo chính sách triển khai. Runtime cần dependency `mssql-python` và các thư viện Linux `libltdl7`, `libkrb5-3`, `libgssapi-krb5-2`; bộ cài native và Containerfile của app đã khai báo chúng.

Chạy migrate để seed hai endpoint còn thiếu vào API Documentation. Patch `add_qcbrother_reports` bảo đảm Pilot nhận ra bản cập nhật cần migrate; không thay đổi metadata DocType. Catalog giữ nguyên endpoint, role và mô tả đã chỉnh trong Desk. Lỗi query/ngày trả HTTP 400, thiếu quyền trả 403, lỗi cấu hình hoặc nguồn SQL trả 503 mà không trả connection string hay thông tin driver.

Kiểm tra logic độc lập bằng `python -m unittest discover -s tests -p test_qcbrother_reports.py`. Khi nâng cấp site, kiểm tra thêm hai URL bằng cùng khoảng ngày và filter trên API .NET nguồn.

Sau khi cài app, chạy `bench --site <site> migrate`. API `qc-inspection-summary` là Server Script; để tạo nó trên site mới, bật `server_script_enabled` và chạy `bench --site <site> execute factory_management.provision.ensure_qc_inspection_summary`.

## Trang QC trong Desk

Sau khi migrate, vào **Website → Web Page**, mở bản ghi **QC** (route `/qc`) để sửa HTML và CSS. Trang được tạo một lần; các lần migrate tiếp theo không ghi đè thay đổi trong Desk. Chỉ **System Manager** được sửa bản ghi QC. Trang `/qc` vẫn mở được cho tablet chưa đăng nhập; đăng ký thiết bị và dữ liệu QC tiếp tục dùng API của app.

Khi phân phối QC cho site khác, xuất bản Web Page đã duyệt từ Desk rồi nhập trên site đích. Nếu site đích chưa có Web Page route `qc`, lần migrate đầu sẽ tạo bản mặc định đi kèm app. JavaScript QC, manifest và service worker vẫn được phát hành cùng mã app. Địa chỉ HTTP trong mạng nội bộ không cho service worker hoạt động trên phần lớn trình duyệt; dùng HTTPS nếu cần mở lại trang khi mất mạng.

Khi thêm microservice khác, có thể nhập URL OpenAPI của dịch vụ vào bản ghi Service. Trình duyệt cần được phép đọc URL đó qua CORS nếu nó nằm ở miền khác Frappe.
