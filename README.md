# Coursera Workspace v7 — hướng dẫn từ A đến Z

Bản này nối dashboard Vercel, Worker/D1, Chrome extension và trình duyệt cloud Modal thành một bộ mã. Dashboard có giao diện sáng/tối, hỗ trợ điện thoại, quản lý tài khoản, nhật ký, lịch sử xác nhận lệnh, hướng dẫn sử dụng và trang khởi động/dừng Cloud Browser.

**Phân biệt:** mã và kiểm thử có sẵn trong gói; triển khai Modal, cấu hình Secret và đăng nhập Coursera là các bước riêng. Bản này không tự chứng nhận hoàn thành khóa học, không tự đăng nhập/nhập OTP hoặc tự nộp bài đánh giá. Trợ lý AI hỗ trợ giải thích/luyện tập. Không hứa chạy 24/7 miễn phí.

## 1. Các thành phần

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| Dashboard | `vercel-dashboard/` | Giao diện quản lý, không lưu ADMIN_TOKEN vào localStorage |
| Backend | `cloud-worker/` | Xác thực, tài khoản, D1, hàng đợi lệnh, proxy API Modal và AI |
| Extension | `extension/` | Điều khiển phát video thực, gửi heartbeat và xác nhận lệnh |
| Cloud Browser | `modal_cloud_extension.py` | Chromium + extension trên máy chủ, noVNC, lưu profile |
| Kiểm thử | `cloud-worker/tests/`, `tests/`, `extension/test_*.js` | Kiểm thử offline và hành vi tích hợp mô phỏng |

Giữ các địa chỉ dự án hiện tại:

- Dashboard: https://coursera-control-center.vercel.app
- Worker: https://coursera-ai-control-v5.hungle06-01-01.workers.dev
- D1: `coursera-control-v5`, ID `66a9abfe-ad79-4805-b8cb-73aee39e2dfb`.
- Modal app: `coursera-cloud-extension-v1`.
- Modal Secret: `coursera-cloud-extension-v1`, environment `main`.
- Volume: `coursera-cloud-extension-profile-v1`.

Không cần khôi phục `coursera-control-runner-v5` đã xóa. Nút Cloud Browser mới dùng API mới, không gọi runner v5.

## 2. Tạo kết nối cloud trên dashboard

1. Mở dashboard → **Cài đặt & kết nối**.
2. Nhập Worker URL và ADMIN_TOKEN hiện tại. Đây là token quản trị ứng dụng, không phải mật khẩu Coursera.
3. **Tài khoản → Tạo tài khoản**, đặt tên `Cloud 01`.
4. Lưu token `ccc_...` vừa hiển thị. Token chỉ hiện một lần; quên thì dùng **Đổi token**.
5. Nếu dùng cả laptop và cloud, tạo `Laptop 01` với token khác. Dùng chung token làm heartbeat và lệnh tranh chấp.

## 3. Cài Modal trên Windows

Giải nén, mở PowerShell tại thư mục chứa `modal_cloud_extension.py`:

```powershell
py -m pip install -r requirements.txt
py -m modal setup
```

Đăng nhập Modal bằng quy trình chính thức nếu máy chưa đăng nhập. Không gửi token Modal hoặc mật khẩu qua chat.

## 4. Tạo Modal Secret

Trong Modal Dashboard, chọn đúng workspace và environment **main**, tạo hoặc cập nhật Secret **coursera-cloud-extension-v1**:

| Tên biến | Nội dung |
|---|---|
| `CLOUDFLARE_WORKER_URL` | `https://coursera-ai-control-v5.hungle06-01-01.workers.dev` |
| `EXTENSION_TOKEN` | Token của `Cloud 01` từ bước 2 |
| `REMOTE_ACCESS_PASSWORD` | Mật khẩu riêng cho màn hình cloud, dài 20–256 ký tự, không xuống dòng |
| `CLOUD_MODAL_TOKEN` | Chuỗi ngẫu nhiên tối thiểu 32 ký tự; dùng cùng giá trị trong Worker |

Tạo hai chuỗi ngẫu nhiên khác nhau trên máy của bạn khi cần:

```powershell
py -c "import secrets; print(secrets.token_urlsafe(32))"
```

Không dùng ADMIN_TOKEN cho mật khẩu màn hình hoặc token API cloud. Profile Volume có cookie đăng nhập nhạy cảm, chỉ bạn quản lý.

## 5. Deploy Modal

Từ đúng thư mục giải nén:

```powershell
py -m modal deploy modal_cloud_extension.py --env main
```

Modal sẽ in HTTPS URL của function **cloud_api**. Sao chép chính URL đó; không dùng URL cũ `coursera-control-check` hoặc URL noVNC.

Tên app và Volume giữ từ v6 để có thể dùng profile đã lưu. Dừng phiên v6 đang chạy trước khi deploy. Không redeploy giữa lúc Chromium đang sử dụng profile.

## 6. Nối Worker với Modal

Mở Cloudflare Dashboard → Workers & Pages → `coursera-ai-control-v5` → Settings → Variables and Secrets:

| Biến | Loại | Giá trị |
|---|---|---|
| `CLOUD_MODAL_ENDPOINT` | Text | HTTPS URL của function `cloud_api` vừa deploy |
| `CLOUD_MODAL_TOKEN` | Secret | Cùng chuỗi đã đặt ở Modal Secret |

Lưu/deploy cấu hình. Nếu backend chưa cập nhật mã v7, triển khai `cloud-worker/` theo bước 9 trước.

Không nhập token API cloud trong frontend. Dashboard gọi Worker bằng ADMIN_TOKEN; Worker gửi token API cloud tới Modal ở phía máy chủ.

## 7. Dùng hoàn toàn bằng dashboard

1. Mở **Trình duyệt cloud → Kiểm tra**. Nếu báo chưa cấu hình, hoàn tất bước 5–6.
2. Chọn `Cloud 01`, chọn 15/45/90/170 phút → **Khởi động cloud**.
3. Chờ “Trình duyệt cloud sẵn sàng”. Khởi động lạnh lần đầu có thể lâu; làm mới trạng thái nếu request timeout, không bấm tạo liên tục.
4. **Mở trình duyệt**. Màn hình từ xa mở ở tab mới (không nhúng iframe).
5. HTTP Basic Auth: username **admin**, password là `REMOTE_ACCESS_PASSWORD`.
6. Đăng nhập Coursera trực tiếp trong Chromium cloud. Tự nhập mật khẩu và OTP khi Coursera yêu cầu.
7. Mở khóa học và một video, mở popup extension → chọn tốc độ, bắt đầu danh sách phát. Autoplay không được tự bật lúc tạo phiên.
8. Về dashboard kiểm tra **heartbeat extension** đã mới, tài khoản báo đúng khóa học. Heartbeat máy chủ và heartbeat extension là hai tín hiệu khác nhau.
9. **Tạm dừng / Tiếp tục / Dừng video** ở Chi tiết tài khoản. Lịch sử lệnh hiển thị “Đang chờ extension”, “Đã thực hiện” hoặc “Thực hiện thất bại”.
10. Khi xong → **Dừng & lưu phiên**. Chờ trạng thái “Đã dừng”, profile “Đã lưu”.

### Tắt laptop có chạy tiếp không?

Có, nếu Chromium thực sự đã chạy trên Modal và còn thời lượng. Extension laptop dừng khi Chrome hoặc laptop tắt. Đóng dashboard/noVNC không tự dừng tác vụ cloud. Phiên tự kết thúc khi hết thời lượng; không tự tạo phiên mới vô hạn.

### Có nhớ đăng nhập không?

Sau khi Chromium đóng bình thường, runner lưu profile vào Volume. Lần sau dùng lại profile. Coursera vẫn có thể yêu cầu đăng nhập lại/2FA; không bảo đảm cookie tồn tại mãi. Kill/timeout đột ngột có thể mất thay đổi gần nhất. Profile chỉ lưu an toàn sau khi Chromium đóng.

### Nhiều tài khoản?

Dashboard quản lý nhiều kết nối laptop. Cloud runner này có **một profile / một phiên cloud đồng thời**, gắn với EXTENSION_TOKEN trong Modal Secret. Muốn đổi tài khoản cloud cần dừng/lưu phiên, đăng xuất Coursera, cập nhật token Secret và deploy lại. Chỉ đổi nhãn dashboard không đổi tài khoản đăng nhập Coursera.

## 8. Cài extension laptop (tùy chọn)

Chrome → `chrome://extensions` → Developer mode → Load unpacked → chọn thư mục `extension/`. Nếu đã có bản cũ, chọn Reload hoặc thay thư mục. Mở Coursera → popup extension → nhập Worker URL và token riêng của `Laptop 01`; cấp quyền truy cập Worker khi Chrome hỏi. Bản v7 tăng version manifest; dispatch trực tiếp trong MV3 vẫn giữ từ bản đã sửa.

## 9. Triển khai backend/dashboard từ bộ mã

### Backend Cloudflare

Cần Node.js hỗ trợ `node:sqlite` để chạy kiểm thử (Node 24 được dùng khi kiểm tra gói này). Chạy trong `cloud-worker/`:

```powershell
npm install
npx wrangler login
npx wrangler d1 execute coursera-control-v5 --remote --file schema-v5.sql
npx wrangler deploy
```

Schema dùng CREATE TABLE IF NOT EXISTS, không xóa dữ liệu cũ. Giữ ADMIN_TOKEN_HASH hiện tại hoặc đặt Secret ADMIN_TOKEN mới do bạn tự quản lý:

```powershell
npx wrangler secret put ADMIN_TOKEN
npx wrangler secret put CLOUD_MODAL_TOKEN
```

Để deploy bằng CLI giữ cấu hình cloud, thêm `CLOUD_MODAL_ENDPOINT` vào vars của `wrangler.jsonc`; cấu hình API key dùng Secrets, không ghi vào mã. File portable không chứa admin hash của triển khai cũ. Kiểm tra lại biến đang có trước khi deploy CLI vì vars trong cấu hình có thể thay thế vars cũ. Không deploy bản portable mà chưa đặt ADMIN_TOKEN hoặc ADMIN_TOKEN_HASH.

### Dashboard Vercel

Trong `vercel-dashboard/`:

```powershell
npx vercel link --project coursera-control-center
npx vercel --prod
```

Chọn đúng team/project hiện có. Không chọn tạo project mới. Dashboard tĩnh không cần build hoặc API key AI. Nếu preview Vercel khác origin, Worker cần thêm origin đó vào DASHBOARD_ORIGIN để kiểm tra kết nối; production hiện tại đã được cho phép.

## 10. Trợ lý AI

Backend hỗ trợ 4 tuyến qua 3 nhà cung cấp, lựa chọn tự động theo đầu vào và thử tuyến tiếp theo khi lỗi khả dụng. Model mặc định được tra tài liệu chính thức; bạn có thể ghi đè bằng biến server:

| Tuyến | Mặc định | Cấu hình |
|---|---|---|
| Groq | `openai/gpt-oss-120b` | Secret GROQ_API_KEY, biến GROQ_MODEL tùy chọn |
| Gemini | `gemini-3.5-flash-lite` | Secret GEMINI_API_KEY, biến GEMINI_MODEL tùy chọn |
| CF Qwen | `@cf/qwen/qwen3-30b-a3b-fp8` | Binding AI, biến CF_QWEN_MODEL tùy chọn |
| CF GLM | `@cf/zai-org/glm-4.7-flash` | Binding AI, biến CF_GLM_MODEL tùy chọn |

Ảnh chỉ gửi tới tuyến đã xác định hỗ trợ ảnh (Gemini). Qwen/Groq/GLM mặc định ở đây là tuyến văn bản. Không gắn nhãn model có thể nhận ảnh khi chưa xác minh. Có binding/key không bảo đảm tài khoản được cấp quyền, quota còn đủ hoặc model luôn hoạt động. Dùng một câu hỏi ngắn trong extension để kiểm tra thực tế.

Nguồn model: https://console.groq.com/docs/models ; https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite ; https://developers.cloudflare.com/changelog/post/2026-04-09-new-workers-ai-models/ .

## 11. Lệnh dự phòng khi dashboard không mở được

```powershell
py -m modal run --env main modal_cloud_extension.py::start --minutes 45
py -m modal run --env main modal_cloud_extension.py::status
py -m modal run --env main modal_cloud_extension.py::stop
```

CLI start dùng cùng controller tuần tự như dashboard. Tác vụ Chromium được spawn trên server. Lệnh status đọc Modal Dict, tránh lỗi status cũ do Volume mount chưa reload.

## 12. Khắc phục lỗi

| Dấu hiệu | Cách kiểm tra |
|---|---|
| 401 ở dashboard | Nhập đúng ADMIN_TOKEN; token cũ không được khôi phục từ trình duyệt |
| Chưa cấu hình Cloud Browser | Đặt CLOUD_MODAL_ENDPOINT/CLOUD_MODAL_TOKEN ở Worker; deploy Modal v7 |
| 401 ở cloud API | Token giữa Worker và Modal khác nhau hoặc dưới 32 ký tự |
| Chọn sai tài khoản cloud | EXTENSION_TOKEN trong Modal thuộc tài khoản khác; chọn đúng Cloud 01 |
| Khởi động trùng bị chặn | Dừng phiên cũ và chờ lưu. Phiên stale vẫn bị khóa đến hết thời lượng + khoảng chờ an toàn |
| Cloud chạy, tài khoản offline | Mở /learn/ trong Chromium, kiểm tra token và popup extension; refresh Coursera |
| Không phát tự động | Nhấn Play trực tiếp nếu browser chặn autoplay; bắt đầu danh sách bằng popup |
| Lệnh pending lâu | Extension chưa nhận hoặc chưa có tab phù hợp; xem khóa học và heartbeat |
| Không mở noVNC | Xem log Modal, mật khẩu Basic Auth, Xvfb/nginx/websockify; không chia sẻ URL |
| Profile chưa lưu | Chờ dừng xong; xem profile_save_error trong log trạng thái, không tạo phiên thứ hai |
| AI lỗi | Xem API key, quyền model, quota, tên model ở Worker; dùng kết quả thật để xác minh |

## 13. Kiểm thử và giới hạn chứng minh

```powershell
node --test cloud-worker/tests/*.test.mjs
node --test extension/test_*.js
py -m unittest discover -s tests -v
```

Kiểm thử offline kiểm tra xác thực, API, D1 giả lập SQLite, lệnh/ack, proxy Modal, vòng đời và tài khoản cloud, extension dispatch, giới hạn tốc độ và cấu trúc gói. Chúng không thay thế phép thử thật đăng nhập Coursera, nghe/xem video trong cloud hoặc kiểm tra lưu cookie qua hai phiên.

Phép thử nghiệm thu thật: mở cloud → đăng nhập → phát → pause/resume từ dashboard và xem ack → đóng Chrome laptop → chờ 2 phút → mở lại dashboard thấy heartbeat mới → dừng/lưu → mở lại phiên kiểm tra profile. Không có bằng chứng đạt nghiệm thu này cho đến khi bạn thực hiện trên Modal đã xác thực.

Xem thêm `docs/KIEN_TRUC.md` và `docs/KIEM_THU.md`.
