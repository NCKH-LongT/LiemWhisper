# -*- coding: utf-8 -*-
"""
Liem STT - Pure HTML Interface (Zero CSS) with Real-Time Audio (RTA)
Displays complete sentences, live audio meter, real-time speech stream,
and full Whisper vs Liem STT comparison.
"""

def get_retro_html() -> str:
    return """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Liem STT - Web Test (HTML Thuần + RTA)</title>
</head>
<body>

    <h1>Hệ Thống Thử Nghiệm Liem STT</h1>
    <p>Nhận dạng giọng nói tiếng Việt chêm tiếng Anh (Code-Switching) và sửa lỗi thuật ngữ.</p>
    <hr>

    <!-- 1. THỬ NGHIỆM ÂM THANH & RTA -->
    <h2>1. Thử nghiệm Âm thanh &amp; Nói Trực Tiếp (RTA)</h2>

    <div>
        <label><b>Cách 1: Ghi âm trực tiếp từ Micro (Có RTA hiển thị trực tiếp):</b></label><br>
        <button type="button" id="recordBtn" onclick="toggleRecord()">Bắt đầu Ghi Âm Micro</button>
        <span id="recordStatus" style="color:red; font-weight:bold;"></span>
    </div>

    <!-- KHU VỰC RTA (REAL-TIME AUDIO & SPEECH STREAM) -->
    <div id="rtaContainer" style="display:none; margin-top:10px; border:1px dashed #666; padding:10px; background:#f9f9f9;">
        <b>[RTA 1 - Âm lượng Micro thời gian thực]:</b><br>
        <progress id="audioLevelBar" value="0" max="100" style="width:300px; height:18px;"></progress>
        <span id="audioLevelText">0%</span>
        <br><br>
        <b>[RTA 2 - Lời nói thời gian thực (Live Speech-to-Text)]:</b><br>
        <div id="liveSpeechText" style="color:blue; font-style:italic; min-height:24px;">(Đang lắng nghe giọng bạn...)</div>
    </div>
    <br>

    <div>
        <label><b>Cách 2: Chọn câu ghi âm mẫu thực tế có sẵn (10 câu ISTQB):</b></label><br>
        <select id="userSampleSelect" onchange="onSelectUserSample()" style="width:100%; max-width:800px;">
            <option value="">-- Bấm vào đây để chọn câu mẫu có sẵn --</option>
            <option value="Recording (3).m4a" data-text="Trong quá trình đánh giá chất lượng phần mềm, QA cần phân tích False Positive Rate, False Negative Rate, Precision, Recall và F1-Score để xác định mức độ chính xác của hệ thống phân loại lỗi.">Câu 1: False Positive Rate, Precision, Recall, F1-Score (Recording 3)</option>
            <option value="Recording (4).m4a" data-text="Khi kiểm thử ứng dụng web, nhóm QA cần đánh giá cơ chế Cross-Origin Resource Sharing (CORS), kiểm tra khả năng chống Cross-Site Request Forgery (CSRF) và xác minh tính an toàn của Content Security Policy (CSP).">Câu 2: CORS, CSRF, CSP (Recording 4)</option>
            <option value="Recording (5).m4a" data-text="Trong quá trình kiểm thử cơ sở dữ liệu, kỹ sư cần kiểm tra Database Normalization, đánh giá hiệu suất Query Optimization, phát hiện N+1 Query Problem và xác minh cơ chế Transaction Isolation.">Câu 3: Database Normalization, Query Optimization, N+1 Query (Recording 5)</option>
            <option value="Recording (6).m4a" data-text="Khi đánh giá hệ thống phân tán, QA cần kiểm tra Service Discovery, xác minh cơ chế Load Balancing, phân tích Network Partitioning và đánh giá khả năng duy trì High Availability.">Câu 4: Service Discovery, Load Balancing, High Availability (Recording 6)</option>
            <option value="Recording (7).m4a" data-text="Trong quá trình kiểm thử mô hình học máy, nhóm nghiên cứu cần đánh giá Overfitting, Underfitting, Feature Extraction, Hyperparameter Tuning và khả năng Model Generalization trên dữ liệu thực tế.">Câu 5: Overfitting, Underfitting, Feature Extraction (Recording 7)</option>
            <option value="Recording (8).m4a" data-text="Khi phát triển hệ thống nhận dạng giọng nói, nhóm nghiên cứu cần phân tích Phoneme Recognition, đánh giá Acoustic Modeling, kiểm tra Language Modeling và xác minh khả năng xử lý Background Noise trong môi trường ghi âm phức tạp.">Câu 6: Phoneme Recognition, Acoustic Modeling (Recording 8)</option>
            <option value="Recording (9).m4a" data-text="Trong quá trình đánh giá dữ liệu huấn luyện AI, chuyên gia cần kiểm tra Data Augmentation, phát hiện Label Noise, đánh giá Sampling Bias và xác minh tính đại diện của Training Distribution so với dữ liệu triển khai thực tế.">Câu 7: Data Augmentation, Label Noise, Sampling Bias (Recording 9)</option>
            <option value="Recording (10).m4a" data-text="Khi kiểm thử hệ thống CI/CD, kỹ sư cần xác minh Build Pipeline, đánh giá cơ chế Automated Deployment, kiểm tra Rollback Strategy và phân tích các lỗi phát sinh trong quá trình Continuous Integration.">Câu 8: Build Pipeline, Automated Deployment, Continuous Integration (Recording 10)</option>
            <option value="Recording (11).m4a" data-text="Trong quá trình đánh giá mô hình nhận dạng thuật ngữ chuyên ngành, nhóm nghiên cứu cần kiểm tra Zero-Shot Learning, phân tích Contrastive Loss, đánh giá Cosine Similarity và xác minh khả năng phân biệt các thuật ngữ thông qua Embedding Space.">Câu 9: Zero-Shot Learning, Contrastive Loss, Cosine Similarity (Recording 11)</option>
            <option value="Recording (12).m4a" data-text="Khi kiểm thử hiệu năng nền tảng trực tuyến, QA cần đo lường Response Time, phân tích Throughput, kiểm tra Latency ở phân vị P95 và P99, đồng thời đánh giá mức tiêu thụ CPU Utilization và Memory Footprint khi hệ thống hoạt động liên tục.">Câu 10: Response Time, Throughput, Latency P95 P99, Memory Footprint (Recording 12)</option>
        </select>
    </div>
    <br>

    <div>
        <label><b>Cách 3: Tải file từ máy tính (.wav, .mp3, .m4a):</b></label><br>
        <input type="file" id="audioFileInput" accept="audio/*" onchange="onFileSelected()">
    </div>
    <br>

    <div>
        <label><b>Nghe lại file âm thanh đã nạp:</b></label><br>
        <audio id="audioPreview" controls style="width:100%; max-width:800px;"></audio>
        <div id="sampleRefText" style="color:#555; font-size:13px; margin-top:4px;"></div>
    </div>
    <br>

    <div>
        <button type="button" id="runAudioBtn" onclick="executeAudioProcess()" style="font-weight:bold; font-size:14px; padding:6px 14px;">Chạy Nhận Dạng &amp; Sửa Lỗi Liem STT</button>
        <span id="audioLoading" style="display:none; color:blue; font-weight:bold;"> Đang xử lý qua Whisper và Liem STT... Xin vui lòng đợi!</span>
    </div>

    <!-- BẢNG KẾT QUẢ ĐỐI CHIẾU HOÀN CHỈNH -->
    <div id="audioResultBox" style="display:none; margin-top:16px;">
        <h3>Kết Quả Đối Chiếu Hoàn Chỉnh:</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="width:100%; max-width:1000px;">
            <tr bgcolor="#eee">
                <th width="35%">Whisper Chép Thô (Câu Hoàn Chỉnh)</th>
                <th width="40%">Liem STT Đã Sửa (Câu Hoàn Chỉnh)</th>
                <th width="25%">Top 5 Thuật Ngữ Âm Học (E0 Retrieval)</th>
            </tr>
            <tr>
                <td valign="top" id="outRawAsr" style="color:#b30000; font-size:14px; line-height:1.6;"></td>
                <td valign="top">
                    <div id="outRevisedAsr" style="font-size:14px; line-height:1.6; color:#006600;"></div>
                    <div id="outChangesList" style="margin-top:10px; font-size:13px; border-top:1px dotted #ccc; padding-top:6px;"></div>
                </td>
                <td valign="top" id="outContrastiveTop5" style="font-size:13px;"></td>
            </tr>
            <tr bgcolor="#f9f9f9">
                <td colspan="3" style="font-size:12px; color:#555;">
                    <b>Thời gian xử lý:</b> <span id="outLatency">0</span> ms | 
                    <b>Mô hình:</b> Whisper-Small + Liem Contrastive Retrieval + Selective Correction
                </td>
            </tr>
        </table>
    </div>
    <hr>

    <!-- 2. THỬ NGHIỆM VĂN BẢN -->
    <h2>2. Thử nghiệm Sửa Lỗi Văn Bản Trực Tiếp (Text Input)</h2>
    <p>Bấm chọn nhanh câu mẫu chép sai hoặc nhập câu bất kỳ:</p>
    <div>
        <button type="button" onclick="setTextSample('Nhóm nghiên cứu cần kiểm tra Tero Swift London và contract steel loads.')">Mẫu 1: Tero Swift London &amp; contract steel loads</button>
        <button type="button" onclick="setTextSample('Cần kiểm tra Rombus Tangerine và các lỗi phát sinh trong continuous interaction.')">Mẫu 2: Rombus Tangerine &amp; continuous interaction</button>
        <button type="button" onclick="setTextSample('Trong kiểm thử phần mềm cần phát hiện phong injection và lỗi bảo mật.')">Mẫu 3: phong injection</button>
    </div>
    <br>
    <textarea id="textInputBox" rows="3" cols="80" placeholder="Nhập câu tiếng Việt có chêm tiếng Anh bị sai vào đây..."></textarea>
    <br>
    <button type="button" onclick="executeTextProcess()" style="font-weight:bold;">Sửa Lỗi Văn Bản</button>
    <button type="button" onclick="document.getElementById('textInputBox').value=''">Xóa</button>
    <span id="textLoading" style="display:none; color:blue;"> Đang phân tích...</span>

    <div id="textResultBox" style="display:none; margin-top:12px;">
        <h3>Kết Quả Sửa Văn Bản:</h3>
        <table border="1" cellpadding="8" cellspacing="0" style="width:100%; max-width:1000px;">
            <tr bgcolor="#eee">
                <th width="45%">Câu Gốc (Bị Sai)</th>
                <th width="55%">Câu Liem STT Đã Sửa (Hoàn Chỉnh)</th>
            </tr>
            <tr>
                <td id="textOrigOut" style="color:#b30000; font-size:14px; line-height:1.5;"></td>
                <td id="textFixedOut" style="color:#006600; font-size:14px; line-height:1.5;"></td>
            </tr>
        </table>
    </div>
    <hr>

    <!-- 3. BẢNG DỮ LIỆU 10 CÂU THỰC TẾ -->
    <h2>3. Bảng Dữ Liệu 10 Câu Ghi Âm Thực Tế (Benchmark)</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="width:100%; max-width:1000px;">
        <tr bgcolor="#eee">
            <th width="5%">STT</th>
            <th width="35%">Câu Gốc (Ground Truth) &amp; File</th>
            <th width="30%">Whisper Chép Sai</th>
            <th width="20%">Liem STT Nhận Diện</th>
            <th width="10%">Thao tác</th>
        </tr>
        <tr>
            <td>1</td>
            <td><b>Recording (3).m4a</b><br>False Positive Rate, False Negative Rate, Precision, Recall, F1-Score</td>
            <td style="color:#b30000;">...vào Positive Ray, Phone, Negative Ray, Position, Recall và F1 Score...</td>
            <td style="color:#006600;"><b>Recall &amp; F1-Score</b></td>
            <td><button type="button" onclick="testSentencePreset('Recording (3).m4a')">Thử câu này</button></td>
        </tr>
        <tr>
            <td>2</td>
            <td><b>Recording (4).m4a</b><br>Cross-Origin Resource Sharing (CORS), CSRF, Content Security Policy (CSP)</td>
            <td style="color:#b30000;">...Cross-Origin Resort Secrets, Cross-Site, Reweb Foggery, Content Security Policy...</td>
            <td style="color:#006600;"><b>Content Security Policy</b></td>
            <td><button type="button" onclick="testSentencePreset('Recording (4).m4a')">Thử câu này</button></td>
        </tr>
        <tr>
            <td>3</td>
            <td><b>Recording (5).m4a</b><br>Database Normalization, Query Optimization, N+1 Query Problem</td>
            <td style="color:#b30000;">...Database Non-Malization, Query of Teamization, M + 1...</td>
            <td style="color:#006600;"><b>Database Normalization, Query Optimization</b></td>
            <td><button type="button" onclick="testSentencePreset('Recording (5).m4a')">Thử câu này</button></td>
        </tr>
        <tr>
            <td>4</td>
            <td><b>Recording (6).m4a</b><br>Service Discovery, Load Balancing, Network Partitioning, High Availability</td>
            <td>Service Discovery, Load Balancing, Network Partitioning, High Availability</td>
            <td style="color:#006600;">Whisper đúng; Liem kiểm duyệt giữ nguyên 100%</td>
            <td><button type="button" onclick="testSentencePreset('Recording (6).m4a')">Thử câu này</button></td>
        </tr>
        <tr>
            <td>8</td>
            <td><b>Recording (10).m4a</b><br>Build Pipeline, Automated Deployment, Rollback Strategy, Continuous Integration</td>
            <td style="color:#b30000;">...View Pipeline, Automatic Deployment, Rombus Tangerine, continuous interaction...</td>
            <td style="color:#006600;"><b>Continuous Integration!</b></td>
            <td><button type="button" onclick="testSentencePreset('Recording (10).m4a')">Thử câu này</button></td>
        </tr>
        <tr>
            <td>9</td>
            <td><b>Recording (11).m4a</b><br>Zero-Shot Learning, Contrastive Loss, Cosine Similarity, Embedding Space</td>
            <td style="color:#b30000;">...Tero Swift London, contract steel loads, Cosine Similarity, Embedding Space...</td>
            <td style="color:#006600;"><b>Zero-Shot Learning &amp; Contrastive Loss</b></td>
            <td><button type="button" onclick="testSentencePreset('Recording (11).m4a')">Thử câu này</button></td>
        </tr>
    </table>

<script>
    var currentAudioBlob = null;
    var mediaRecorder = null;
    var audioChunks = [];

    // RTA variables
    var audioContext = null;
    var analyser = null;
    var microphoneStream = null;
    var rtaAnimationId = null;
    var recognition = null;
    var isRecording = false;

    // 1. SELECT SAMPLE
    function onSelectUserSample() {
        var select = document.getElementById('userSampleSelect');
        var fileName = select.value;
        if (!fileName) return;

        var opt = select.options[select.selectedIndex];
        document.getElementById('sampleRefText').innerText = "Câu gốc tham chiếu: " + (opt.getAttribute('data-text') || "");
        
        var audioUrl = '/user_audio/' + encodeURIComponent(fileName);
        var preview = document.getElementById('audioPreview');
        preview.src = audioUrl;

        fetch(audioUrl)
            .then(function(res) { return res.blob(); })
            .then(function(blob) {
                currentAudioBlob = new File([blob], fileName, { type: 'audio/m4a' });
            })
            .catch(function(e) {
                console.error("Lỗi tải file mẫu:", e);
            });
    }

    // 2. FILE UPLOAD
    function onFileSelected() {
        var input = document.getElementById('audioFileInput');
        if (input.files && input.files[0]) {
            currentAudioBlob = input.files[0];
            var preview = document.getElementById('audioPreview');
            preview.src = URL.createObjectURL(currentAudioBlob);
            document.getElementById('sampleRefText').innerText = "Tệp đã chọn: " + currentAudioBlob.name + " (" + Math.round(currentAudioBlob.size / 1024) + " KB)";
        }
    }

    // 3. RTA RECORDING (AUDIO METER + LIVE SPEECH STREAM)
    function toggleRecord() {
        var btn = document.getElementById('recordBtn');
        var status = document.getElementById('recordStatus');
        var rtaBox = document.getElementById('rtaContainer');

        if (isRecording) {
            // STOP RECORDING
            isRecording = false;
            btn.innerText = 'Bắt đầu Ghi Âm Micro';
            status.innerText = 'Đã dừng ghi âm! Đang phân tích câu hoàn chỉnh...';

            if (recognition) {
                try { recognition.stop(); } catch(e) {}
            }
            if (rtaAnimationId) {
                cancelAnimationFrame(rtaAnimationId);
            }
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
            return;
        }

        // START RECORDING
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('Trình duyệt không hỗ trợ truy cập Micro!');
            return;
        }

        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(function(stream) {
                microphoneStream = stream;
                isRecording = true;
                audioChunks = [];

                // Show RTA panel
                rtaBox.style.display = 'block';
                document.getElementById('liveSpeechText').innerText = '(Đang lắng nghe trực tiếp, hãy nói vào micro...)';
                btn.innerText = '⏹ DỪNG GHI ÂM (HOÀN THÀNH)';
                status.innerText = '● Đang ghi âm & phân tích RTA...';

                // Setup MediaRecorder
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = function(e) {
                    if (e.data.size > 0) audioChunks.push(e.data);
                };
                mediaRecorder.onstop = function() {
                    if (microphoneStream) {
                        microphoneStream.getTracks().forEach(function(track) { track.stop(); });
                    }
                    var blob = new Blob(audioChunks, { type: 'audio/webm' });
                    currentAudioBlob = new File([blob], "microphone_live.webm", { type: 'audio/webm' });
                    var preview = document.getElementById('audioPreview');
                    preview.src = URL.createObjectURL(blob);
                    document.getElementById('sampleRefText').innerText = "Bản thu trực tiếp từ Micro (" + Math.round(blob.size / 1024) + " KB)";
                    
                    // Auto-execute final Whisper + Liem pipeline
                    executeAudioProcess();
                };
                mediaRecorder.start();

                // Setup RTA Level Meter (AudioContext + AnalyserNode)
                try {
                    window.AudioContext = window.AudioContext || window.webkitAudioContext;
                    audioContext = new AudioContext();
                    var source = audioContext.createMediaStreamSource(stream);
                    analyser = audioContext.createAnalyser();
                    analyser.fftSize = 256;
                    source.connect(analyser);

                    var dataArray = new Uint8Array(analyser.frequencyBinCount);
                    function updateRtaMeter() {
                        if (!isRecording) return;
                        analyser.getByteFrequencyData(dataArray);
                        var sum = 0;
                        for (var i = 0; i < dataArray.length; i++) {
                            sum += dataArray[i];
                        }
                        var average = sum / dataArray.length;
                        var levelPct = Math.min(100, Math.round((average / 128) * 100));

                        document.getElementById('audioLevelBar').value = levelPct;
                        document.getElementById('audioLevelText').innerText = levelPct + '%';
                        rtaAnimationId = requestAnimationFrame(updateRtaMeter);
                    }
                    updateRtaMeter();
                } catch(errA) {
                    console.warn("RTA AudioContext warning:", errA);
                }

                // Setup RTA Live Speech-to-Text stream (Web Speech API)
                var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
                if (SpeechRec) {
                    recognition = new SpeechRec();
                    recognition.continuous = true;
                    recognition.interimResults = true;
                    recognition.lang = 'vi-VN';

                    recognition.onresult = function(event) {
                        var fullTranscript = '';
                        for (var i = 0; i < event.results.length; ++i) {
                            fullTranscript += event.results[i][0].transcript + ' ';
                        }
                        fullTranscript = fullTranscript.trim();
                        if (fullTranscript) {
                            document.getElementById('liveSpeechText').innerText = '» ' + fullTranscript;
                        }
                    };
                    recognition.onerror = function(e) {
                        console.warn("RTA SpeechRecognition error:", e);
                    };
                    recognition.start();
                } else {
                    document.getElementById('liveSpeechText').innerText = '(Trình duyệt này không hỗ trợ SpeechRecognition API, nhưng audio vẫn được ghi âm đầy đủ)';
                }
            })
            .catch(function(err) {
                alert('Không thể mở micro: ' + err.message);
                isRecording = false;
            });
    }

    // 4. EXECUTE FULL AUDIO PIPELINE (WHISPER + LIEM)
    function executeAudioProcess() {
        if (!currentAudioBlob) {
            alert('Vui lòng chọn 1 câu mẫu, tải file lên, hoặc ghi âm micro trước!');
            return;
        }

        document.getElementById('audioLoading').style.display = 'inline';
        document.getElementById('runAudioBtn').disabled = true;

        var formData = new FormData();
        formData.append('file', currentAudioBlob);
        formData.append('engine', 'proposal');

        fetch('/api/process_audio', {
            method: 'POST',
            body: formData
        })
        .then(function(res) {
            if (!res.ok) throw new Error('HTTP error ' + res.status);
            return res.json();
        })
        .then(function(data) {
            document.getElementById('audioLoading').style.display = 'none';
            document.getElementById('runAudioBtn').disabled = false;
            document.getElementById('audioResultBox').style.display = 'block';

            // 1. Raw ASR full sentence
            var rawText = data.raw_asr_transcript || data.raw_asr || data.original_transcript || '(Trống)';
            document.getElementById('outRawAsr').innerText = rawText;

            // 2. Revised full sentence (highlight corrected terms)
            var revisedText = data.revised_transcript || data.revised_text || rawText;
            var highlighted = revisedText;

            if (data.accepted_changes && data.accepted_changes.length > 0) {
                data.accepted_changes.forEach(function(c) {
                    if (c.replacement) {
                        // Highlight replacement in bold green
                        highlighted = highlighted.split(c.replacement).join('<b><font color="green">' + c.replacement + '</font></b>');
                    }
                });
            }
            document.getElementById('outRevisedAsr').innerHTML = highlighted;

            // 3. Accepted changes details
            var chgHtml = '';
            if (data.accepted_changes && data.accepted_changes.length > 0) {
                chgHtml = '<b>Chi tiết sửa đổi:</b><br>';
                data.accepted_changes.forEach(function(c) {
                    chgHtml += '➔ <font color="red"><s>' + c.original_span + '</s></font> sửa thành <b><font color="green">' + c.replacement + '</font></b><br>';
                });
            } else {
                chgHtml = '<i>(Không có cụm từ nào bị sửa ẩu - câu được giữ nguyên)</i>';
            }
            document.getElementById('outChangesList').innerHTML = chgHtml;

            // 4. Contrastive Top 5
            var topList = [];
            if (data.contrastive_retrieval) {
                topList = data.contrastive_retrieval.top_all || data.contrastive_retrieval.candidates || [];
            }
            var topHtml = '<ol style="margin:0; padding-left:18px;">';
            if (topList && topList.length > 0) {
                topList.forEach(function(item) {
                    var sim = Math.round((item.similarity || 0) * 100);
                    topHtml += '<li><b>' + item.term + '</b> (' + sim + '%)</li>';
                });
            } else {
                topHtml += '<li>Không có dữ liệu Top 5</li>';
            }
            topHtml += '</ol>';
            document.getElementById('outContrastiveTop5').innerHTML = topHtml;

            // 5. Latency
            var latency = data.total_latency_ms || data.latency_ms || 0;
            document.getElementById('outLatency').innerText = Math.round(latency);
        })
        .catch(function(err) {
            document.getElementById('audioLoading').style.display = 'none';
            document.getElementById('runAudioBtn').disabled = false;
            alert('Lỗi xử lý âm thanh: ' + err.message);
        });
    }

    // 5. TEXT PROCESS
    function setTextSample(text) {
        document.getElementById('textInputBox').value = text;
    }

    function executeTextProcess() {
        var text = document.getElementById('textInputBox').value.trim();
        if (!text) {
            alert('Vui lòng nhập câu vào ô trước!');
            return;
        }

        document.getElementById('textLoading').style.display = 'inline';

        fetch('/api/process_text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, engine: 'proposal' })
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            document.getElementById('textLoading').style.display = 'none';
            document.getElementById('textResultBox').style.display = 'block';

            var orig = data.original_transcript || data.raw_asr || text;
            var fixed = data.revised_transcript || data.revised_text || orig;

            // Highlight in bold green
            if (data.accepted_changes && data.accepted_changes.length > 0) {
                data.accepted_changes.forEach(function(c) {
                    if (c.replacement) {
                        fixed = fixed.split(c.replacement).join('<b><font color="green">' + c.replacement + '</font></b>');
                    }
                });
            }

            document.getElementById('textOrigOut').innerText = orig;
            document.getElementById('textFixedOut').innerHTML = fixed;
        })
        .catch(function(err) {
            document.getElementById('textLoading').style.display = 'none';
            alert('Lỗi: ' + err.message);
        });
    }

    // 6. BENCHMARK PRESET CLICK
    function testSentencePreset(fileName) {
        var select = document.getElementById('userSampleSelect');
        select.value = fileName;
        onSelectUserSample();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        setTimeout(function() {
            executeAudioProcess();
        }, 300);
    }
</script>

</body>
</html>
"""
