## FTP-download-file-rar
- UI responsive khi thu nhỏ cửa sổ (không ẩn button).
- Nhớ Host/Port/User/Password và thư mục tải/giải nén vào `~/.ftp_rar_gui.json`.
- Tải xuống có thể **resume** nếu tệp tồn tại.
- Thanh tiến trình tự động chuyển **indeterminate → determinate** khi biết tổng dung lượng.
- Giải nén an toàn, chặn path traversal.
## Cài đặt
- Tải project.
- Dùng CMD/ Powershell chạy lệnh: pip install -r requirements.txt để cài thư viện hỗ trợ.
- Dùng CMD/ Powershell chạy lệnh: python main.py để chạy ứng dụng.
> Lưu ý: Cần cài đặt backend giải nén RAR (unrar/unar/bsdtar) và có trong PATH. Dùng file install_unrar.bat để cài đặt backend giải nén RAR.
## Giao diện
<img width="1051" height="762" alt="image" src="https://github.com/user-attachments/assets/cf1ec4cc-c35c-4fd6-b7cb-8fb0b16e281d" />



