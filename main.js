// (1) Sayfa yüklendiğinde init()'i başlatacak
document.addEventListener('DOMContentLoaded', init);

// (2) Tüm setup adımlarını buradan çağıracağız
async function init() {
  await initCameraList();
  bindSourceSelection();
  bindFolderSelector();
  bindResizeSlider();
  bindStartStopButtons();
  bindTabSwitching();
  bindCoordinateFileInput();
  // bindVideoFileInput();
  bindVideoSelector();
  bindCreateCoordinateFile();
  bindSelectorCoordinateFileInput();
  bindSelectorStart();
  bindThemeToggle();
  
}

// (A) Kamera listesini dolduracak fonksiyon
async function initCameraList() {
  // 1) cameraSelect elementini al
  const cameraSelect = document.getElementById('cameraSelect');
  // (İsterseniz eski seçenekleri temizleyin)
  cameraSelect.innerHTML = '';

  // 2) Python'dan bağlı kameraları çekin
  const cameras = await eel.find_camera_devices()();

  // 3) Her bir kamera için option oluşturup dropdown'a ekleyin
  cameras.forEach(camIdx => {
    const opt = document.createElement('option');
    opt.value = camIdx;
    opt.textContent = `Kamera ${camIdx}`;
    cameraSelect.appendChild(opt);
  });
}

// (B) Kamera / Video kaynak seçim radyo butonları
function bindSourceSelection() {
  const cameraSelect    = document.getElementById('cameraSelect');
  const selectVideoBtn  = document.getElementById('selectVideoBtn');
  const videoPathInput  = document.getElementById('videoPath');
  const ipRadio        = document.getElementById('ipSource');
  const ipUrlInput     = document.getElementById('ipUrl');
  const cameraRadio     = document.getElementById('cameraSource');
  const videoRadio      = document.getElementById('videoSource');

  // başlangıçta kamera seçili
  cameraSelect.disabled   = false;
  selectVideoBtn.disabled = true;
  videoPathInput.disabled = true;
  ipUrlInput.disabled     = true;

  cameraRadio.addEventListener('change', () => {
    cameraSelect.disabled   = false;
    selectVideoBtn.disabled = true;
    videoPathInput.disabled = true;
    ipUrlInput.disabled     = true;
  });
  videoRadio.addEventListener('change', () => {
    cameraSelect.disabled   = true;
    selectVideoBtn.disabled = false;
    videoPathInput.disabled = false;
    ipUrlInput.disabled     = true;
  });
  ipRadio.addEventListener('change', () => {
    cameraSelect.disabled   = true;
    selectVideoBtn.disabled = true;
    videoPathInput.disabled = true;
    ipUrlInput.disabled     = false;
  });
}


// (C) Klasör Seç butonunu bağlar
function bindFolderSelector() {
  const selectBtn = document.getElementById('selectFolder');
  const folderPathInput = document.getElementById('folderPath');

  selectBtn.addEventListener('click', async () => {
    // Python tarafındaki filedialog’u aç
    const chosenPath = await eel.select_folder()();
    if (chosenPath) {
      folderPathInput.value = chosenPath;
    }
  });
}

// (D) Slider’ı ve label’ı senkronize eden fonksiyon
function bindResizeSlider() {
  const slider = document.getElementById('resizeSlider');
  const label  = document.getElementById('resizeValue');

  // Başlangıç değeri
  label.textContent = `${slider.value}%`;

  // Kullanıcı slider’ı hareket ettirdikçe label güncellensin
  slider.addEventListener('input', () => {
    label.textContent = `${slider.value}%`;
  });
}

// (E) Başla / Durdur butonlarını ve get_frame döngüsünü yönetir
// main.js

function bindStartStopButtons() {
  const startBtn        = document.getElementById('startBtn');
  const stopBtn         = document.getElementById('stopBtn');
  const errorBox        = document.getElementById('errorBox');

  const cameraSelect    = document.getElementById('cameraSelect');
  const cameraRadio     = document.getElementById('cameraSource');
  const videoRadio      = document.getElementById('videoSource');
  const ipRadio         = document.getElementById('ipSource');

  const videoPathInput  = document.getElementById('videoPath');
  const ipUrlInput      = document.getElementById('ipUrl');
  const coordinateInput = document.getElementById('coordinatePath');
  const resizeSlider    = document.getElementById('resizeSlider');
  const stateNameInput  = document.getElementById('stateName');
  const videoFeed       = document.getElementById('videoFeed');
  const statusImage     = document.getElementById('statusImage');
  const parkingStatus   = document.getElementById('parkingStatus');

  let videoInterval   = null;

  startBtn.addEventListener('click', async () => {
    errorBox.textContent = '';

    const coordPath = coordinateInput.dataset.path;
    if (!coordPath) {
      errorBox.textContent = 'Koordinat dosyası seçilmedi!';
      return;
    }

    // Kaynak seçimi
    let cameraSource;
    if (cameraRadio.checked) {
      if (!cameraSelect.value) {
        errorBox.textContent = 'Kamera seçilmedi!';
        return;
      }
      cameraSource = parseInt(cameraSelect.value, 10);

    } else if (videoRadio.checked) {
      if (!videoPathInput.value) {
        errorBox.textContent = 'Video dosyası seçilmedi!';
        return;
      }
      cameraSource = videoPathInput.value;

    } else if (ipRadio.checked) {
      const url = ipUrlInput.value.trim();
      if (!url) {
        errorBox.textContent = 'Lütfen IP kamera URL’si girin!';
        return;
      }
      cameraSource = url;

    } else {
      errorBox.textContent = 'Lütfen bir kaynak seçin!';
      return;
    }

    console.log('Seçilen kaynak tipi:',
      cameraRadio.checked ? 'USB Kamera' :
      videoRadio.checked  ? 'Video Dosyası' :
      'IP Kamera'
    );
    console.log('cameraSource değeri:', cameraSource);

    // start_video çağrısı
    const resizeVal = parseInt(resizeSlider.value, 10);
    const res = await eel.start_video(cameraSource, coordPath, resizeVal)();
    if (res.error) {
      errorBox.textContent = res.error;
      return;
    }

    startBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    // diğer kontrolleri devre dışı bırak
    cameraRadio.disabled = videoRadio.disabled = ipRadio.disabled = true;
    cameraSelect.disabled = videoPathInput.disabled = ipUrlInput.disabled = true;
    coordinateInput.disabled = resizeSlider.disabled = stateNameInput.disabled = true;

    // Döngüyü başlat
    if (videoInterval) clearInterval(videoInterval);
    videoInterval = setInterval(async () => {
      const stateName = stateNameInput.value;
      const resp = await eel.get_frame(stateName)();
      if (!resp.success) {
        errorBox.textContent = resp.message || 'Hata';
        clearInterval(videoInterval);
        return;
      }

      videoFeed.src  = `data:image/jpeg;base64,${resp.frame}`;
      statusImage.src = `data:image/jpeg;base64,${resp.overlay}`;

      parkingStatus.innerHTML = '';
      for (const area in resp.parkingStatus) {
        const areaDiv = document.createElement('div');
        areaDiv.className = 'area';
        areaDiv.innerHTML = `<h4>${area}</h4>` +
          Object.entries(resp.parkingStatus[area])
                .map(([cell, st]) =>
                  `<span class="cell ${st==='BOS'?'free':'occupied'}">${cell}: ${st}</span>`
                ).join('');
        parkingStatus.appendChild(areaDiv);
      }
    }, 100);
  });

  stopBtn.addEventListener('click', async () => {
    await eel.stop_video()();
    if (videoInterval) clearInterval(videoInterval);

    // durdurulduğunda buton görünüşünü geri al
    startBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    // kontrolleri tekrar aktif et
    cameraRadio.disabled = videoRadio.disabled = ipRadio.disabled = false;
    cameraSelect.disabled = !cameraRadio.checked;
    videoPathInput.disabled = !videoRadio.checked;
    ipUrlInput.disabled = !ipRadio.checked;
    coordinateInput.disabled = false;
    resizeSlider.disabled = false;
    stateNameInput.disabled = false;

  });

  async function updateFrame() {
    const resp = await eel.get_frame(stateNameInput.value)();
    if (!resp.success) {
      errorBox.textContent = resp.message || 'Hata';
      clearInterval(videoInterval);
      return;
    }
    document.getElementById('videoFeed').src  = `data:image/jpeg;base64,${resp.frame}`;
    document.getElementById('statusImage').src = `data:image/jpeg;base64,${resp.overlay}`;
    // …durum panosunu güncelle…
  }

  // başlangıçta “durdur” gizli olsun
  stopBtn.classList.add('hidden');

}





// (F) Tab butonlarına tıklanınca ilgili içerikleri göster/gizle
function bindTabSwitching() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const selectorTab = document.getElementById('selectorTab');
  const mainContent = document.querySelector('.content-area');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      // Tüm butonlardan .active sınıfını kaldır
      tabBtns.forEach(b => b.classList.remove('active'));
      // Tıklanan butona ekle
      btn.classList.add('active');

      // İçerikleri gizle
      selectorTab.style.display = 'none';
      mainContent.style.display = 'none';

      // Hangi tab seçildiyse göster
      if (btn.dataset.tab === 'selector') {
        selectorTab.style.display = 'block';
      } else {
        mainContent.style.display = 'flex';
      }
    });
  });
}

// (G) Koordinat dosyası seçildiğinde handle_coordinate_file'i çağırır
function bindCoordinateFileInput() {
  const coordFileInput = document.getElementById('coordinateFile');
  const coordPathEl    = document.getElementById('coordinatePath');
  const errorBox       = document.getElementById('errorBox');

  coordFileInput.addEventListener('change', async (e) => {
    if (!e.target.files.length) return;              // Dosya yoksa çık
    const file = e.target.files[0];

    // 1) Görsel için görünürdeki metni güncelle
    coordPathEl.value = file.name;

    // 2) Dosyayı oku
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload  = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('Dosya okunamadı'));
      reader.readAsText(file);
    });

    // 3) Python tarafına gönder
    const res = await eel.handle_coordinate_file(content, file.name)();
    if (res.success) {
      // 4) Başarılıysa gerçek path'i dataset'e kaydet
      coordPathEl.dataset.path = res.path;
      errorBox.textContent = '';
      const coords = await eel.get_coordinates()();
      // document.getElementById('coordinateStatus').innerText =
      //   JSON.stringify(coords, null, 2);
    } else {
      // 5) Hata varsa ekranda göster
      errorBox.textContent = 'Koordinat dosyası yüklenemedi: ' + res.error;
    }
  });
}

// main.js’in en altına veya bindVideoFileInput’ın hemen üstüne ekleyin:
function bindVideoSelector() {
  const btn      = document.getElementById('selectVideoBtn');
  const pathIn   = document.getElementById('videoPath');
  const errorBox = document.getElementById('errorBox');

  btn.addEventListener('click', async () => {
    errorBox.textContent = '';
    const filePath = await eel.select_video()();  // Python'dan gerçek yol
    if (!filePath) {
      errorBox.textContent = 'Video seçilmedi!';
      return;
    }
    pathIn.value = filePath;
  });
}




// (H) Video dosyası seçildiğinde sadece adı gösterir
function bindVideoFileInput() {
  const videoFileInput = document.getElementById('videoFile');
  const videoPathInput  = document.getElementById('videoPath');
  const errorBox        = document.getElementById('errorBox');

  videoFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Dosya adı görünür input'a yaz
    videoPathInput.value = file.name;
    // Özellikle hata kutusunu temizleyelim
    errorBox.textContent = '';
  });
}





function bindCreateCoordinateFile() {
  const btn       = document.getElementById('createCoordinateFile');
  const nameInput = document.getElementById('fileNaming');
  const errorBox  = document.getElementById('errorBox');
  const mainCoordPathIn = document.getElementById('coordinatePath');
  const selectorCoordAddr = document.getElementById('selectorCoordinateAddress');

  btn.addEventListener('click', async () => {
    errorBox.textContent = '';
    const fileName = nameInput.value.trim();
    if (!fileName) {
      return errorBox.textContent = 'Lütfen bir dosya adı girin!';
    }

    // Python fonksiyonunu çağırıyoruz
    const res = await eel.create_coordinate_file(fileName)();
    if (!res.success) {
      errorBox.textContent = res.message || 'Dosya oluşturulamadı!';
      return;
    }

    // Oluşan gerçek path'i hem ana panele hem selector tab'a yaz
    mainCoordPathIn.value = fileName;
    mainCoordPathIn.dataset.path = res.path;

    selectorCoordAddr.value = fileName;
    selectorCoordAddr.dataset.path = res.path;

    errorBox.textContent = res.message; // "Dosyanız başarılı bir şekilde oluşturuldu..."
  });
}

function bindSelectorCoordinateFileInput() {
  const fileInput = document.getElementById('selectorCoordinateFile');
  const addressIn = document.getElementById('selectorCoordinateAddress');
  const errorBox  = document.getElementById('errorBox');

  fileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    addressIn.value = file.name;
    errorBox.textContent = '';

    // Dosyayı oku
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload  = () => resolve(reader.result);
      reader.onerror = () => reject(new Error('Dosya okunamadı'));
      reader.readAsText(file);
    });

    // Python'a gönder
    const res = await eel.handle_coordinate_file(content, file.name)();
    if (res.success) {
      addressIn.dataset.path = res.path;
    } else {
      errorBox.textContent = 'Koordinat dosyası yüklenemedi: ' + res.error;
    }
  });
}

// (I) Selector sekmesindeki Başlat butonunu bağlar
// ———————— (2) bindSelectorStart fonksiyonu ————————
function bindSelectorStart() {
  const selectorStartBtn  = document.getElementById('selectorStartBtn');
  const selectorCoordIn   = document.getElementById('selectorCoordinateAddress');
  const selectorAreaIn    = document.getElementById('selectorAreaName');
  const selectorCellIn    = document.getElementById('selectorCellName');
  const cameraRadio       = document.getElementById('cameraSource');
  const videoRadio   = document.getElementById('videoSource');
  const ipRadio           = document.getElementById('ipSource');
  const videoPathInput = document.getElementById('videoPath');
  const ipUrlInput     = document.getElementById('ipUrl');
  const cameraSelect      = document.getElementById('cameraSelect');
  
  const errorBox          = document.getElementById('errorBox');

  selectorStartBtn.addEventListener('click', async () => {
    errorBox.textContent = '';

    // 1) JSON ve input kontrolleri
    const coordFile = selectorCoordIn.dataset.path || selectorCoordIn.value;
    if (!coordFile) {
      return errorBox.textContent = 'Koordinat dosyası seçilmedi!';
    }
    const areaName = selectorAreaIn.value.trim();
    if (!areaName) {
      return errorBox.textContent = 'Alan adı boş olamaz!';
    }
    const cellName = selectorCellIn.value.trim();
    if (!cellName) {
      return errorBox.textContent = 'Hücre adı boş olamaz!';
    }

    // 2) Kaynak seçimi
    let source;
    if (cameraRadio.checked) {
      const cam = cameraSelect.value;
      if (!cam) {
        return errorBox.textContent = 'Kamera seçilmedi!';
      }
      source = parseInt(cam, 10);
    } else {
      const vid = videoPathInput.value;
      if (!vid) {
        return errorBox.textContent = 'Video dosyası seçilmedi!';
      }
      source = vid;
    }

    // 3) start_selector çağrısı (4 argüman!)
    try {
      const res = await eel.start_selector(source, coordFile, areaName, cellName)();
      if (!res.success) {
        errorBox.textContent = res.error;
      } else {
        errorBox.textContent = `Eklenen hücreler: ${res.cells.join(', ')}`;
        // document.getElementById('selectorStatus').innerText =
        //   'Eklenen Hücreler:\n' + res.cells.map(c => c).join(', ');
      }
    } catch (err) {
      errorBox.textContent = 'Selector hata: ' + err.message;
    }
  });
}


function bindThemeToggle() {
  const btn = document.getElementById('themeToggle');
  btn.addEventListener('click', () => {
    document.body.classList.toggle('dark-theme');
    const isDark = document.body.classList.contains('dark-theme');
    btn.textContent = isDark ? 'Light Mode' : 'Dark Mode';
    // Optionally persist choice:
    localStorage.setItem('darkMode', isDark ? '1' : '0');
  });

  // On load, restore:
  if (localStorage.getItem('darkMode') === '1') {
    document.body.classList.add('dark-theme');
    btn.textContent = 'Light Mode';
  }
}



