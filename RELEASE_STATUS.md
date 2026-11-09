# Trạng thái bàn giao v7 — 24/10/2026

## Đã triển khai

- Dashboard production: https://coursera-control-center.vercel.app
- Vercel project: `coursera-control-center`, ID `prj_9Y4tjbHCJsKQggHBDEkI9eUQYiz9`.
- Production deployment cuối: `dpl_H2pgb3zJYDF2Pn3cRZkQdYH2CChy`.
- Worker `coursera-ai-control-v5`: upload v7 được Cloudflare chấp nhận HTTP 200.
- `/control/health` đã mở trên trình duyệt thật và trả `ok: true`, `version: 7`, `database: true`.
- Các binding đang có được kế thừa khi cập nhật Worker. D1 không chạy lệnh xóa/migration trong lần triển khai này; đã kiểm tra ba bảng tài khoản/lệnh/nhật ký tồn tại.

## Đã kiểm tra

- 25 kiểm thử Node backend qua.
- 4 chương trình kiểm thử extension qua.
- 14 kiểm thử Python offline qua.
- Cú pháp JavaScript dashboard và Python runner hợp lệ.
- Mở bản dashboard production trong trình duyệt, kiểm tra tổng quan, trang cloud, hướng dẫn và chuyển sáng/tối. Không thấy lỗi từ mã ứng dụng trong lượt kiểm tra này.
- Gọi thật model Cloudflare GLM `@cf/zai-org/glm-4.7-flash` bằng tài khoản Cloudflare: trả đáp án `4` cho phép tính `2+2`, HTTP 200. Đây là kiểm tra nhà cung cấp, không phải kiểm thử AI qua extension đã đăng nhập.

## Chưa được nghiệm thu thực tế

- **Modal chưa được deploy/xác thực trong lượt này.** Mã Cloud Browser API đã viết và kiểm thử controller offline; cần bạn deploy trên máy đã đăng nhập Modal, tạo Secret và đặt hai biến ở Worker theo README bước 3–6.
- Chưa xác minh đăng nhập Coursera, phát video trong cloud, pause/resume xuyên suốt dashboard → Worker → extension cloud, hoặc lưu cookie qua hai phiên thật.
- Groq/Gemini chưa có API key trong binding Worker đã kiểm tra. Không tuyên bố đủ bốn tuyến AI đã hoạt động.
- Chưa kiểm tra trực quan trên viewport điện thoại. CSS có bố cục responsive, nhưng môi trường không tải được Chromium cục bộ để chạy bộ kiểm tra viewport tự động; không coi đó là kết quả kiểm thử mobile đã qua.
- Cloud runner hỗ trợ một profile/một phiên đồng thời, mỗi phiên 5–170 phút; không phải giải pháp chạy 24/7 tự gia hạn.
- Không tích hợp tự nộp bài đánh giá có chấm điểm; thao tác bài nộp do người học thực hiện.

## Việc cần làm để bật cloud

1. Tạo tài khoản `Cloud 01` trên dashboard, lưu token extension riêng.
2. Tạo/cập nhật Modal Secret `coursera-cloud-extension-v1` gồm bốn biến trong README.
3. Chạy `py -m modal deploy modal_cloud_extension.py --env main`.
4. Đặt `CLOUD_MODAL_ENDPOINT` (URL function cloud_api) và Secret `CLOUD_MODAL_TOKEN` trong Worker.
5. Dashboard → Trình duyệt cloud → Kiểm tra → chọn tài khoản → Khởi động cloud → Mở trình duyệt.
6. Đăng nhập Coursera trực tiếp, bắt đầu phát bằng extension và thực hiện phép thử nghiệm thu cuối README.
