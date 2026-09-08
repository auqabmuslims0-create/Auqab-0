#!/data/data/com.termux/files/usr/bin/sh

# منع نوم الهاتف
termux-wake-lock

# الدخول لمجلد المشروع
cd /data/data/com.termux/files/home/husayniyyah_market

# بدء خادم Flask
tmux has-session -t app 2>/dev/null || tmux new-session -d -s app 'python app.py'

# بدء cloudflared مع حفظ الرابط في ملف
tmux has-session -t tunnel 2>/dev/null || tmux new-session -d -s tunnel 'cloudflared tunnel --url http://127.0.0.1:5000 2>&1 | tee /data/data/com.termux/files/home/tunnel_url.txt'

echo "تم تشغيل الخادم والنفق. الرابط سيظهر بعد قليل."
