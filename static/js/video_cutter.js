let ffmpegInstance = null;
let videoFile = null;
let videoURL = null;
let videoElement = null;
let startSlider, endSlider, startLabel, endLabel, durationLabel;
let currentDuration = 0;
let maxDuration = 60; // ثانية

async function loadFFmpeg() {
    if (ffmpegInstance) return ffmpegInstance;

    console.log('بدء تحميل FFmpeg...');
    if (typeof FFmpeg === 'undefined') {
        throw new Error('FFmpeg غير معرّف. تأكد من تحميل مكتبة ffmpeg.min.js');
    }

    const { createFFmpeg, fetchFile } = FFmpeg;
    if (!createFFmpeg || !fetchFile) {
        throw new Error('createFFmpeg أو fetchFile غير موجودين. تحقق من إصدار المكتبة');
    }

    ffmpegInstance = createFFmpeg({
        log: true
        // لم نحدد corePath ليعتمد على الافتراضي (يُحمّل من unpkg تلقائيًا)
    });
    await ffmpegInstance.load();
    console.log('تم تحميل FFmpeg بنجاح');
    return ffmpegInstance;
}

function initVideoCutter(inputElement) {
    inputElement.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file || !file.type.startsWith('video/')) return;
        
        videoFile = file;
        if (videoURL) URL.revokeObjectURL(videoURL);
        videoURL = URL.createObjectURL(file);
        
        const modal = document.getElementById('videoCutterModal');
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        videoElement = document.getElementById('cutterVideo');
        videoElement.src = videoURL;
        
        videoElement.onloadedmetadata = function() {
            currentDuration = videoElement.duration;
            maxDuration = Math.min(60, currentDuration);
            durationLabel.textContent = `مدة الفيديو الكلية: ${formatTime(currentDuration)}`;
            
            startSlider.min = 0;
            startSlider.max = currentDuration;
            startSlider.value = 0;
            endSlider.min = 0;
            endSlider.max = currentDuration;
            endSlider.value = Math.min(maxDuration, currentDuration);
            
            updateTimeDisplay();
            validateDuration();
        };
        
        function updateTimeDisplay() {
            const start = parseFloat(startSlider.value);
            const end = parseFloat(endSlider.value);
            startLabel.textContent = formatTime(start);
            endLabel.textContent = formatTime(end);
            const selectedDuration = end - start;
            document.getElementById('selectedDuration').textContent = formatTime(selectedDuration);
            validateDuration();
        }
        
        startSlider.addEventListener('input', function() {
            if (parseFloat(startSlider.value) >= parseFloat(endSlider.value)) {
                startSlider.value = Math.max(0, parseFloat(endSlider.value) - 0.1);
            }
            if (parseFloat(endSlider.value) - parseFloat(startSlider.value) > maxDuration) {
                endSlider.value = Math.min(parseFloat(startSlider.value) + maxDuration, currentDuration);
            }
            updateTimeDisplay();
        });
        
        endSlider.addEventListener('input', function() {
            if (parseFloat(endSlider.value) <= parseFloat(startSlider.value)) {
                endSlider.value = Math.min(parseFloat(startSlider.value) + 0.1, currentDuration);
            }
            if (parseFloat(endSlider.value) - parseFloat(startSlider.value) > maxDuration) {
                startSlider.value = Math.max(0, parseFloat(endSlider.value) - maxDuration);
            }
            updateTimeDisplay();
        });
        
        document.getElementById('confirmCutBtn').onclick = async function() {
            const start = parseFloat(startSlider.value);
            const end = parseFloat(endSlider.value);
            if (end - start > maxDuration + 0.01) {
                alert(`المدة المحددة تتجاوز ${maxDuration} ثانية`);
                return;
            }
            if (end - start <= 0) {
                alert('يرجى تحديد مدة صالحة');
                return;
            }
            
            try {
                const cutBlob = await cutVideo(videoFile, start, end);
                const newFile = new File([cutBlob], `cut_${videoFile.name}`, { type: 'video/mp4' });
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(newFile);
                inputElement.files = dataTransfer.files;
                
                modalInstance.hide();
                showToast('تم قص الفيديو بنجاح', 'success');
            } catch (error) {
                console.error('فشل القص:', error);
                alert('فشل قص الفيديو: ' + error.message);
            }
        };
    });
}

async function cutVideo(file, start, end) {
    const ffmpeg = await loadFFmpeg();
    const { fetchFile } = FFmpeg;
    if (!fetchFile) throw new Error('fetchFile غير موجود');

    const inputName = 'input.' + file.name.split('.').pop();
    const outputName = 'output.mp4';

    console.log('كتابة ملف الإدخال...');
    ffmpeg.FS('writeFile', inputName, await fetchFile(file));

    console.log('تنفيذ أوامر ffmpeg...');
    await ffmpeg.run(
        '-i', inputName,
        '-ss', start.toString(),
        '-to', end.toString(),
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-crf', '23',
        '-c:a', 'aac',
        '-movflags', '+faststart',
        outputName
    );

    console.log('قراءة الملف الناتج...');
    const data = ffmpeg.FS('readFile', outputName);
    const blob = new Blob([data.buffer], { type: 'video/mp4' });

    // تنظيف
    ffmpeg.FS('unlink', inputName);
    ffmpeg.FS('unlink', outputName);

    return blob;
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function validateDuration() {
    const start = parseFloat(startSlider.value);
    const end = parseFloat(endSlider.value);
    const selected = end - start;
    const confirmBtn = document.getElementById('confirmCutBtn');
    const warning = document.getElementById('durationWarning');
    if (selected > maxDuration + 0.01) {
        confirmBtn.disabled = true;
        warning.textContent = `المدة المحددة (${formatTime(selected)}) تتجاوز الحد الأقصى ${maxDuration} ثانية`;
        warning.classList.remove('d-none');
    } else {
        confirmBtn.disabled = false;
        warning.classList.add('d-none');
    }
}

window.initVideoCutter = initVideoCutter;
