/*
 * J.A.R.V.I.S. — Windows baslatici
 *
 * Masaustundeki simgeye ciftiklandiginda su isi yapar:
 *
 *   1. Panel zaten calisiyor mu diye bakar — calisiyorsa yalnizca tarayiciyi
 *      acar, ikinci bir kopya baslatmaz.
 *   2. WSL icinde `jarvis-panel` calistirir, kendi konsolunu devrederek: panel
 *      ciktisi bu pencerede akar ve Ctrl-C ile durur. Kullanicinin bugunku
 *      aliskanligi bu, degistirmeye gerek yok.
 *   3. Arka planda portu yoklar; panel gercekten cevap vermeye basladiginda
 *      tarayiciyi acar.
 *
 * Hazir olmayi TCP baglantisiyla degil, /health'e HTTP istegiyle olcuyoruz.
 * Sebebi somut: WSL2'de bayat bir `netsh portproxy` kaydi ayni portu 0.0.0.0
 * uzerinden dinlemeye devam ediyor, TCP baglantisi aciliyor ve panel olu
 * oldugu halde "hazir" gorunuyor. /health cevabini okumak bu tuzagi eliyor.
 */
#define WIN32_LEAN_AND_MEAN
#define _CRT_RAND_S            /* rand_s icin, stdlib.h'den ONCE */
#include <stdlib.h>
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define VARSAYILAN_PORT   8765
#define BEKLEME_SANIYE    300      /* ilk acilis model yukleyebilir */
#define YOKLAMA_MS        700

static wchar_t g_dagitim[160]  = L"";           /* bos = varsayilan dagitim */
static wchar_t g_klasor[512]   = L"~/jarvis";
static wchar_t g_komut[2048]   = L"";           /* doluysa kendi komutunuz  */
static wchar_t g_jeton[64]     = L"";           /* bos = her acilista uret  */
/*
 * Jeton ini'den mi geldi, yoksa biz mi urettik? Fark onemli: urettigimiz
 * jeton yalnizca BIZIM baslattigimiz panelde gecerli. Zaten calisan bir
 * panel varsa onun jetonunu bilemeyiz, ve uydurdugumuz jetonla adres acmak
 * kullaniciyi yine "jeton gerekli" sayfasina goturur.
 */
static int     g_jeton_ayarlandi = 0;
static int     g_port          = VARSAYILAN_PORT;
static int     g_port_verildi  = 0;   /* ini'de acikca yazildi mi */
static int     g_tarayici      = 1;
/* Watchdog yeniden baslatmasi gorunur pencere/tarayici acmamali. */
static int     g_watchdog      = 0;
/* Kendi penceresinde mi acilsin, yoksa varsayilan tarayicida sekme olarak mi. */
static int     g_uygulama      = 1;
/* Acilis girisi. 0 yapilirsa panel dogrudan gelir. */
static int     g_intro         = 1;
/*
 * Pencere olcusu ve tam ekran.
 *
 * Panel 1920x1080 icin tasarlandi; daha kucuk bir pencerede sutunlar
 * sikisiyor. Varsayilan artik o olcu, ve "tamekran = 1" ile kenarliksiz
 * aciliyor — masaustunde bir programdan beklenen sey bu, tarayici
 * penceresinden degil.
 */
static int     g_genislik      = 1920;
static int     g_yukseklik     = 1080;
static int     g_tamekran      = 1;
/*
 * Panelin nerede calistigi.
 *
 *   wsl     — eski yol. Panel WSL icinde; bu program wsl.exe cagiriyor.
 *   windows — panel dogrudan Windows'ta, kendi Python'uyla.
 *
 * Windows modunda WSL hic gerekmiyor: ne dagitim, ne interop, ne de her
 * yeniden baslatmada degisen bir sanal ag ve portproxy zinciri. Windows
 * kurulumu bu satiri "windows" yaziyor.
 */
#define MOD_WSL      0
#define MOD_WINDOWS  1
static int     g_mod           = MOD_WSL;
/* Windows modunda calistirilacak Python. Bos = klasordeki .venv. */
static wchar_t g_python[512]   = L"";

/* ------------------------------------------------------------------ yardim */

static void yaz(const char *metin)
{
    fputs(metin, stdout);
    fflush(stdout);
}

static void cizgi(void)
{
    yaz("============================================================\n");
}

static void ini_yolu(wchar_t *hedef, size_t adet);

/* exe'nin bulundugu klasor (sondaki ters bolu dahil) */
static void exe_klasoru(wchar_t *hedef, size_t adet)
{
    DWORD n = GetModuleFileNameW(NULL, hedef, (DWORD)adet);
    if (n == 0 || n >= adet) { hedef[0] = L'\0'; return; }
    wchar_t *son = wcsrchr(hedef, L'\\');
    if (son) son[1] = L'\0';
}

static void kirp(wchar_t *s)
{
    size_t n = wcslen(s);
    while (n && (s[n-1] == L'\r' || s[n-1] == L'\n' || s[n-1] == L' ' || s[n-1] == L'\t'))
        s[--n] = L'\0';
    size_t bas = 0;
    while (s[bas] == L' ' || s[bas] == L'\t') bas++;
    if (bas) memmove(s, s + bas, (wcslen(s + bas) + 1) * sizeof(wchar_t));
}

/*
 * jarvis.ini — exe'nin yanindaki istege bagli ayar dosyasi. Yoksa
 * varsayilanlar kullanilir; olmasi zorunlu degil.
 */
static void ini_yolu(wchar_t *hedef, size_t adet)
{
    exe_klasoru(hedef, adet);
    wcsncat(hedef, L"jarvis.ini", adet - wcslen(hedef) - 1);
}

static void ayarlari_oku(void)
{
    wchar_t yol[MAX_PATH];
    ini_yolu(yol, MAX_PATH);

    FILE *f = _wfopen(yol, L"rt, ccs=UTF-8");
    if (!f) return;

    wchar_t satir[2048];
    while (fgetws(satir, 2048, f)) {
        kirp(satir);
        if (satir[0] == L'\0' || satir[0] == L'#' || satir[0] == L';' || satir[0] == L'[')
            continue;
        wchar_t *esit = wcschr(satir, L'=');
        if (!esit) continue;
        *esit = L'\0';
        wchar_t *anahtar = satir, *deger = esit + 1;
        kirp(anahtar); kirp(deger);

        if (!_wcsicmp(anahtar, L"dagitim"))
            wcsncpy(g_dagitim, deger, 159), g_dagitim[159] = L'\0';
        else if (!_wcsicmp(anahtar, L"klasor"))
            wcsncpy(g_klasor, deger, 511), g_klasor[511] = L'\0';
        else if (!_wcsicmp(anahtar, L"komut"))
            wcsncpy(g_komut, deger, 2047), g_komut[2047] = L'\0';
        else if (!_wcsicmp(anahtar, L"jeton")) {
            wcsncpy(g_jeton, deger, 63);
            g_jeton[63] = L'\0';
            g_jeton_ayarlandi = (g_jeton[0] != L'\0');
        }
        else if (!_wcsicmp(anahtar, L"port")) {
            g_port = _wtoi(deger) > 0 ? _wtoi(deger) : VARSAYILAN_PORT;
            g_port_verildi = 1;
        }
        else if (!_wcsicmp(anahtar, L"tarayici"))
            g_tarayici = (deger[0] == L'0') ? 0 : 1;
        else if (!_wcsicmp(anahtar, L"uygulama"))
            g_uygulama = (deger[0] == L'0') ? 0 : 1;
        else if (!_wcsicmp(anahtar, L"intro"))
            g_intro = (deger[0] == L'0') ? 0 : 1;
        else if (!_wcsicmp(anahtar, L"mod"))
            g_mod = (!_wcsicmp(deger, L"windows")) ? MOD_WINDOWS : MOD_WSL;
        else if (!_wcsicmp(anahtar, L"python"))
            wcsncpy(g_python, deger, 511), g_python[511] = L'\0';
        else if (!_wcsicmp(anahtar, L"tamekran"))
            g_tamekran = (deger[0] == L'0') ? 0 : 1;
        else if (!_wcsicmp(anahtar, L"genislik")) {
            int v = _wtoi(deger);
            if (v >= 800) g_genislik = v;
        }
        else if (!_wcsicmp(anahtar, L"yukseklik")) {
            int v = _wtoi(deger);
            if (v >= 600) g_yukseklik = v;
        }
    }
    fclose(f);
}

/* Watchdog normal masaustu tiklamasiyla ayni exe'yi kullanir, fakat panel
 * penceresini acmasi kullanicinin kendi kendine aciliyor diye gormesine yol
 * acar. Komut satiri yalnizca bu baslatma kaynagini ayirir; asistan secmez. */
static void komut_satirini_oku(void)
{
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) return;
    for (int i = 1; i < argc; i++) {
        if (!_wcsicmp(argv[i], L"--watchdog")) {
            g_watchdog = 1;
            g_tarayici = 0;
        }
    }
    LocalFree(argv);
}

/* ---------------------------------------------------------------- jeton */

/*
 * Panel, .env icinde JARVIS_PANEL_TOKEN varsa jeton istiyor. Baslatici bunu
 * bilemedigi icin jetonsuz adresi aciyor ve kullanici panel yerine "jeton
 * gerekli" sayfasini goruyordu.
 *
 * Cozum: jetonu tahmin etmeye calismak yerine biz belirliyoruz. Panele
 * --jeton ile veriyoruz, ayni degeri adrese koyuyoruz; boylece .env'de ne
 * yazarsa yazsin ikisi her zaman ortusuyor.
 */
static void jeton_uret(wchar_t *hedef, size_t adet)
{
    static const wchar_t harfler[] =
        L"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    const size_t taban = 62;
    size_t uzunluk = adet - 1;
    if (uzunluk > 20) uzunluk = 20;

    for (size_t i = 0; i < uzunluk; i++) {
        unsigned int deger = 0;
        /* rand_s Windows'ta kriptografik uretece bagli; basarisiz olursa
           jetonsuz devam etmektense zayif bir yedek kullaniyoruz — panel
           yalnizca 127.0.0.1'de dinliyor. */
        if (rand_s(&deger) != 0)
            deger = (unsigned int)(GetTickCount64() + i * 2654435761u);
        hedef[i] = harfler[deger % taban];
    }
    hedef[uzunluk] = L'\0';
}

/*
 * Uretilen jetonu jarvis.ini'ye yazar; boylece BIR KEZ uretilir ve bir daha
 * degismez.
 *
 * Her acilista yeni jeton uretmek yanlisti: adres surekli degisiyordu, yer
 * imine eklenemiyordu, ve tarayicida duran eski adres calismiyordu. Jeton
 * gizli tutulmak icin var, her seferinde yenilenmek icin degil.
 *
 * Satir satir kopyalayip yalnizca 'jeton' satirini degistiriyoruz: dosyanin
 * geri kalani (kullanicinin kendi ayarlari, yorumlar) oldugu gibi kalmali.
 */
#define INI_EN_FAZLA_SATIR  400

static int jeton_kaydet(const wchar_t *jeton)
{
    wchar_t yol[MAX_PATH];
    ini_yolu(yol, MAX_PATH);

    static wchar_t satirlar[INI_EN_FAZLA_SATIR][1024];
    int adet = 0;
    int yazildi = 0;

    FILE *f = _wfopen(yol, L"rt, ccs=UTF-8");
    if (f) {
        while (adet < INI_EN_FAZLA_SATIR && fgetws(satirlar[adet], 1024, f)) {
            /* Satir sonlarini burada duselim; yazarken tek bicimde ekleyecegiz. */
            size_t n = wcslen(satirlar[adet]);
            while (n && (satirlar[adet][n-1] == L'\n' || satirlar[adet][n-1] == L'\r'))
                satirlar[adet][--n] = L'\0';
            adet++;
        }
        fclose(f);
    }

    FILE *c = _wfopen(yol, L"wt, ccs=UTF-8");
    if (!c) return 0;

    for (int i = 0; i < adet; i++) {
        wchar_t kopya[1024];
        wcsncpy(kopya, satirlar[i], 1023); kopya[1023] = L'\0';
        kirp(kopya);
        /* Yorum olmayan bir 'jeton = ...' satirini degistir. */
        if (!yazildi && kopya[0] != L';' && kopya[0] != L'#'
            && !_wcsnicmp(kopya, L"jeton", 5)) {
            const wchar_t *p = kopya + 5;
            while (*p == L' ' || *p == L'\t') p++;
            if (*p == L'=') {
                fwprintf(c, L"jeton = %ls\n", jeton);
                yazildi = 1;
                continue;
            }
        }
        fwprintf(c, L"%ls\n", satirlar[i]);
    }
    if (!yazildi) {
        if (adet == 0) fwprintf(c, L"[jarvis]\n");
        fwprintf(c, L"jeton = %ls\n", jeton);
    }
    fclose(c);
    return 1;
}

/* ------------------------------------------------------------------- ag */

/*
 * Panel gercekten cevap veriyor mu? Yalnizca port acik mi diye bakmak
 * yeterli degil (bkz. dosya basindaki portproxy notu), o yuzden /health'e
 * istek atip cevabi okuyoruz.
 */
/*
 * panel_hazir()'in yan urunu: calisan panel jeton istiyor mu?
 *  -1 bilinmiyor · 0 istemiyor · 1 istiyor
 */
static int g_uzak_jeton_ister = -1;

/*
 * "Baglanti kabul edildi ama panel cevabi gelmedi" kac kez ust uste oldu?
 *
 * Bu sayacin tek bir amaci var: bayat portproxy'yi ERKEN yakalamak. Panel
 * henuz acilmadiysa baglanti REDDEDILIR; kabul edilip cevapsiz kalmasi
 * baska bir seyin o portu dinledigini soyler, ki WSL2'de bunun neredeyse
 * tek sebebi olu bir WSL adresine yonlendiren netsh kaydidir. Bunu 5
 * dakikalik zaman asimini bekleyip soylemek yerine hemen soyluyoruz.
 */
static int g_kabul_cevap_yok = 0;

static int panel_hazir(int port)
{
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return 0;

    DWORD zaman_asimi = 1500;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&zaman_asimi, sizeof(zaman_asimi));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char *)&zaman_asimi, sizeof(zaman_asimi));

    struct sockaddr_in adres;
    memset(&adres, 0, sizeof(adres));
    adres.sin_family = AF_INET;
    adres.sin_port = htons((u_short)port);
    adres.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    if (connect(s, (struct sockaddr *)&adres, sizeof(adres)) != 0) {
        /* Reddedildi: henuz kimse dinlemiyor. Normal, panel aciliyor. */
        closesocket(s);
        g_kabul_cevap_yok = 0;
        return 0;
    }

    /* Baglanti kabul edildi. Bundan sonraki her cikis yolu sayaci
       artirmali: bayat bir portproxy baglantiyi kabul edip send sirasinda
       da sifirlayabiliyor, ve o dal erken donerse teshis hic tetiklenmiyor
       — tam da yakalamak istedigimiz durumu kaciriyorduk. */
    char tampon[1024];
    int toplam = 0;
    char istek[256];
    int n = snprintf(istek, sizeof(istek),
                     "GET /health HTTP/1.0\r\nHost: localhost:%d\r\n"
                     "Connection: close\r\n\r\n", port);
    if (send(s, istek, n, 0) > 0) {
        int okunan;
        while (toplam < (int)sizeof(tampon) - 1 &&
               (okunan = recv(s, tampon + toplam, sizeof(tampon) - 1 - toplam, 0)) > 0)
            toplam += okunan;
    }
    closesocket(s);
    tampon[toplam > 0 ? toplam : 0] = '\0';

    /* 200 + govdede "ok" — ikisi birden olmadan hazir saymiyoruz. */
    int hazir = toplam > 0 && strstr(tampon, "200") != NULL
                && strstr(tampon, "\"ok\"") != NULL;
    if (hazir) {
        /* /health jeton isteyip istemedigini soyluyor; degerini degil. */
        if (strstr(tampon, "\"jeton\": true") || strstr(tampon, "\"jeton\":true"))
            g_uzak_jeton_ister = 1;
        else if (strstr(tampon, "\"jeton\": false") || strstr(tampon, "\"jeton\":false"))
            g_uzak_jeton_ister = 0;
    }
    if (hazir) g_kabul_cevap_yok = 0;
    else       g_kabul_cevap_yok++;    /* kabul edildi, panel cevabi yok */
    return hazir;
}

/*
 * Bu portta bir netsh portproxy kaydi var mi?
 *
 * Okumak yonetici gerektirmiyor. Cikti Windows'un OEM kod sayfasinda
 * gelebilir ama biz yalnizca port numarasini ariyoruz — rakamlar her
 * kod sayfasinda ayni.
 */
static int portproxy_var(int port)
{
    /* netsh.exe mutlak yolla cagriliyor. PATH'e guvenmek iki sebeple kotu:
       bozuk bir PATH'te arac sessizce bulunamiyor, ve ayni adi tasiyan
       baska bir program once gelebiliyor. Sistem dizini ikisini de cozer. */
    wchar_t sistem[MAX_PATH];
    UINT n = GetSystemDirectoryW(sistem, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return 0;

    wchar_t komut[MAX_PATH + 80];
    _snwprintf(komut, MAX_PATH + 80,
               L"\"%ls\\netsh.exe\" interface portproxy show v4tov4", sistem);

    FILE *boru = _wpopen(komut, L"rt");
    if (!boru) return 0;

    char aranan[16];
    snprintf(aranan, sizeof(aranan), "%d", port);

    char satir[512];
    int bulundu = 0;
    while (fgets(satir, sizeof(satir), boru)) {
        if (strstr(satir, aranan)) { bulundu = 1; break; }
    }
    _pclose(boru);
    return bulundu;
}

static void portproxy_teshisi(int port)
{
    yaz("\n");
    yaz("  ------------------------------------------------------------\n");
    printf("  ! %d portunu baska bir sey dinliyor ve panel cevabi vermiyor.\n", port);
    yaz("\n");
    if (portproxy_var(port)) {
        printf("    Sebep bulundu: bu portta bir 'netsh portproxy' kaydi var.\n");
        yaz("\n");
        yaz("    WSL'in IP adresi her yeniden baslatmada degisir; kural eski\n");
        yaz("    adreste kalir ve 0.0.0.0'i dinledigi icin LOCALHOST dahil her\n");
        yaz("    istegi yakalayip olu bir adrese gonderir. Tarayici bunu\n");
        yaz("    ERR_CONNECTION_RESET diye gosterir.\n");
    } else {
        yaz("    Bu portta bir portproxy kaydi gorunmuyor; baska bir program\n");
        yaz("    portu tutuyor olabilir.\n");
    }
    yaz("\n");
    yaz("    COZUM - PowerShell'i YONETICI olarak acip:\n");
    yaz("\n");
    printf("      netsh interface portproxy delete v4tov4 "
           "listenport=%d listenaddress=0.0.0.0\n", port);
    yaz("\n");
    yaz("    Telefondan da baglanmak istiyorsaniz silmek yerine guncelleyin:\n");
    yaz("      wsl -- bash -lc 'cd ~/jarvis && "
        "powershell.exe -ExecutionPolicy Bypass -File scripts/windows-yonlendirme.ps1'\n");
    yaz("  ------------------------------------------------------------\n\n");
}

/* ------------------------------------------------------- uygulama penceresi */

/*
 * J.A.R.V.I.S. bir sekmede degil, kendi penceresinde acilsin.
 *
 * Chromium tabanli tarayicilarin "--app=" kipi tam bunu veriyor: adres
 * cubugu yok, sekme seridi yok, gorev cubugunda kendi girisi ve kendi
 * simgesi var (simgeyi sayfanin favicon'undan aliyor — panel /favicon.ico
 * sunuyor). Kullanicinin gozunde bir program; altta hala tanidik bir
 * olusturucu var, ki bu iyi: panel zaten bir web arayuzu.
 *
 * Edge Windows 10/11'de her zaman kurulu, o yuzden ek bir kurulum yok.
 * Hicbiri bulunamazsa varsayilan tarayiciya dusuyoruz — sekmede acilir ama
 * calisir; bir pencere suslemesi icin paneli hic acmamak sacma olurdu.
 */
static int dosya_var(const wchar_t *yol)
{
    DWORD ozellik = GetFileAttributesW(yol);
    return ozellik != INVALID_FILE_ATTRIBUTES
           && !(ozellik & FILE_ATTRIBUTE_DIRECTORY);
}

static int tarayici_bul(wchar_t *hedef, size_t adet)
{
    static const wchar_t *KALIPLAR[] = {
        L"%ls\\Microsoft\\Edge\\Application\\msedge.exe",
        L"%ls\\Google\\Chrome\\Application\\chrome.exe",
        L"%ls\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
    };
    static const wchar_t *KOKLER[] = {
        L"ProgramFiles(x86)", L"ProgramFiles", L"LOCALAPPDATA",
    };

    for (size_t k = 0; k < sizeof(KOKLER) / sizeof(*KOKLER); k++) {
        wchar_t kok[MAX_PATH];
        if (GetEnvironmentVariableW(KOKLER[k], kok, MAX_PATH) == 0) continue;
        for (size_t i = 0; i < sizeof(KALIPLAR) / sizeof(*KALIPLAR); i++) {
            _snwprintf(hedef, adet, KALIPLAR[i], kok);
            if (dosya_var(hedef)) return 1;
        }
    }
    /* Son care: PATH. Nadiren orada olur ama bakmak bedava. */
    if (SearchPathW(NULL, L"msedge.exe", NULL, (DWORD)adet, hedef, NULL) > 0)
        return 1;
    if (SearchPathW(NULL, L"chrome.exe", NULL, (DWORD)adet, hedef, NULL) > 0)
        return 1;
    hedef[0] = L'\0';
    return 0;
}

static int uygulama_penceresi_ac(const wchar_t *adres)
{
    wchar_t tarayici[MAX_PATH];
    if (!tarayici_bul(tarayici, MAX_PATH)) return 0;

    /* Ayri profil: kendi gorev cubugu girisi olsun ve kullanicinin normal
       gezinmesine (sekmeler, oturumlar) hic dokunmasin. */
    wchar_t profil[MAX_PATH] = L"";
    wchar_t yerel[MAX_PATH];
    if (GetEnvironmentVariableW(L"LOCALAPPDATA", yerel, MAX_PATH) > 0)
        _snwprintf(profil, MAX_PATH, L" --user-data-dir=\"%ls\\JARVIS\\pencere\"", yerel);

    /* Acilis girisinin sesi calabilsin. Tarayicilar sayfa icinde bir
       kullanici hareketi olmadan ses calmayi engelliyor; masaustu simgesine
       tiklamak sayilmiyor. Bu kendi penceremiz ve kendi profilimiz oldugu
       icin izni burada veriyoruz — kullanicinin normal gezinmesine
       dokunmuyor. */
    /* Tam ekran: kenarlik da yok, gorev cubugu da ustte degil. Panel
       1920x1080 icin tasarlandi; tam ekran degilse en azindan o olcude
       aciliyor, boylece sutunlar sikismiyor. */
    const wchar_t *tam = g_tamekran ? L" --start-fullscreen" : L"";
    wchar_t komut[4096];
    _snwprintf(komut, 4096,
               L"\"%ls\" --app=\"%ls\" --window-size=%d,%d --window-position=0,0"
               L"%ls --autoplay-policy=no-user-gesture-required%ls",
               tarayici, adres, g_genislik, g_yukseklik, tam, profil);

    STARTUPINFOW baslangic;
    PROCESS_INFORMATION surec;
    memset(&baslangic, 0, sizeof(baslangic));
    baslangic.cb = sizeof(baslangic);
    if (!CreateProcessW(NULL, komut, NULL, NULL, FALSE,
                        CREATE_NO_WINDOW, NULL, NULL, &baslangic, &surec))
        return 0;
    CloseHandle(surec.hProcess);
    CloseHandle(surec.hThread);
    return 1;
}

static void adresi_kur(wchar_t *hedef, size_t adet, int port)
{
    const wchar_t *ek = g_intro ? L"" : L"&intro=0";
    if (g_jeton[0] != L'\0')
        _snwprintf(hedef, adet, L"http://localhost:%d/?token=%ls%ls", port, g_jeton, ek);
    else
        _snwprintf(hedef, adet, L"http://localhost:%d/?%ls", port,
                   g_intro ? L"" : L"intro=0");
}

static void tarayici_ac(int port)
{
    wchar_t adres[256];
    adresi_kur(adres, 256, port);
    wprintf(L"  Adres: %ls\n", adres);

    if (g_uygulama && uygulama_penceresi_ac(adres)) {
        yaz("  Kendi penceresinde aciliyor (sekme yok, adres cubugu yok).\n");
        return;
    }
    if (g_uygulama)
        yaz("  ! Uygulama penceresi acilamadi (Edge/Chrome bulunamadi);\n"
            "    varsayilan tarayicida aciliyor.\n");
    ShellExecuteW(NULL, L"open", adres, NULL, NULL, SW_SHOWNORMAL);
}

/* Panel ayaga kalkinca tarayiciyi acan arka plan is parcacigi. */
/*
 * Kac ust uste "kabul edildi ama cevap yok"tan sonra teshis yazilsin.
 * ~7 saniye: acilis sirasindaki gecici bir durumu yakalamayacak kadar uzun,
 * kullaniciyi bos yere bekletmeyecek kadar kisa.
 */
#define TESHIS_ESIGI 10

static DWORD WINAPI bekle_ve_ac(LPVOID veri)
{
    (void)veri;
    int gecen = 0;
    int teshis_yazildi = 0;
    while (gecen < BEKLEME_SANIYE * 1000) {
        Sleep(YOKLAMA_MS);
        gecen += YOKLAMA_MS;
        if (panel_hazir(g_port)) {
            yaz("\n  > Panel hazir, tarayici aciliyor...\n\n");
            if (g_tarayici) tarayici_ac(g_port);
            return 0;
        }
        /* Bir sey portu dinliyor ama panel degil — beklemenin anlami yok,
           panel acilsa bile o baglantiyi alamayacak. Hemen soyle. */
        if (!teshis_yazildi && g_kabul_cevap_yok >= TESHIS_ESIGI) {
            teshis_yazildi = 1;
            portproxy_teshisi(g_port);
        }
    }
    if (!teshis_yazildi)
        yaz("\n  ! Panel bu sure icinde acilmadi. Yukaridaki ciktiya bakin.\n\n");
    return 1;
}

/* ------------------------------------------------------------------ wsl */

static int wsl_bulundu(wchar_t *yol, size_t adet)
{
    return SearchPathW(NULL, L"wsl.exe", NULL, (DWORD)adet, yol, NULL) > 0;
}

/*
 * Calistirilacak komut satirini kurar.
 *
 * Bash betiginde bilerek hic cift tirnak yok: butun betik Windows komut
 * satirinda cift tirnak icinde gidiyor, icine bir tane daha girse ayrisma
 * bozulurdu.
 */
/*
 * Windows modu: panel dogrudan burada calisiyor.
 *
 * Arada kabuk yok. Klasordeki .venv'in Python'u bir modul olarak paneli
 * baslatiyor, ve calisma klasoru projenin kendisi oluyor — .env ORADAN
 * okundugu icin bu onemli: baska bir klasorden baslatilan panel butun
 * ayarlari gormeden acilir.
 */
static void windows_komutu_kur(wchar_t *hedef, size_t adet)
{
    wchar_t python[512];
    if (g_python[0] != L'\0')
        wcsncpy(python, g_python, 511), python[511] = L'\0';
    else
        _snwprintf(python, 512, L"%ls\\.venv\\Scripts\\python.exe", g_klasor);

    wchar_t jeton_arg[96] = L"";
    if (g_jeton[0] != L'\0')
        _snwprintf(jeton_arg, 96, L" --jeton %ls", g_jeton);

    _snwprintf(hedef, adet,
               L"\"%ls\" -m jarvis.web.cli --port %d%ls",
               python, g_port, jeton_arg);
}


static void komut_kur(wchar_t *hedef, size_t adet)
{
    wchar_t betik[2048];

    if (g_mod == MOD_WINDOWS && g_komut[0] == L'\0') {
        windows_komutu_kur(hedef, adet);
        return;
    }

    if (g_komut[0] != L'\0') {
        /* Kullanici komutu tamamen devraldi: --jeton enjekte etmiyoruz,
           kendi satirini bozmamak icin. Jetonu ini'ye yazmasi gerekir. */
        wcsncpy(betik, g_komut, 2047);
        betik[2047] = L'\0';
    } else {
        wchar_t jeton_arg[96] = L"";
        if (g_jeton[0] != L'\0')
            _snwprintf(jeton_arg, 96, L" --jeton %ls", g_jeton);
        _snwprintf(betik, 2048,
                   L"cd %ls || { echo; echo HATA: %ls klasoru bulunamadi.; "
                   L"echo jarvis.ini icindeki klasor satirini duzeltin.; exit 9; }; "
                   L"[ -f .venv/bin/activate ] && . .venv/bin/activate; "
                   L"command -v %ls-panel >/dev/null || { echo; "
                   L"echo HATA: %ls-panel bulunamadi. Once: pip install -e .; exit 10; }; "
                   L"exec jarvis-panel --port %d%ls",
                   g_klasor, g_klasor, g_port, jeton_arg);
    }

    if (g_dagitim[0] != L'\0')
        _snwprintf(hedef, adet, L"wsl.exe -d %ls -- bash -lc \"%ls\"", g_dagitim, betik);
    else
        _snwprintf(hedef, adet, L"wsl.exe -- bash -lc \"%ls\"", betik);
}

/* ----------------------------------------------------------------- main */

#define ASISTAN_ADI L"J.A.R.V.I.S."

int main(void)
{
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleTitleW(ASISTAN_ADI);
    /* Tamponlamayi kapat: cikti bir dosyaya yonlendirildiginde (kullanici
       bize log gonderirken) blok tamponlu oluyor ve pencere kapanirken son
       satirlar kayboluyor — tam da okumak istedigimiz satirlar. */
    setvbuf(stdout, NULL, _IONBF, 0);

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        yaz("! Winsock baslatilamadi.\n");
        return 1;
    }

    ayarlari_oku();
    /* INI normal kullanıcı açılışını belirler; watchdog bayrağı en son gelip
       tarayıcıyı kesin olarak bastırır. */
    komut_satirini_oku();
    /* Jeton BIR KEZ uretilir ve jarvis.ini'ye yazilir; sonraki her acilista
       ayni deger okunur. Adres sabit kaliyor, yer imine eklenebiliyor, ve
       tarayicida acik duran eski sekme calismaya devam ediyor. */
    int jeton_yeni = 0;
    if (g_jeton[0] == L'\0' && g_komut[0] == L'\0') {
        jeton_uret(g_jeton, 21);
        jeton_yeni = jeton_kaydet(g_jeton);
        g_jeton_ayarlandi = jeton_yeni;
    }

    cizgi();
    wprintf(L"  %ls  ·  Baslatici\n", ASISTAN_ADI);
    cizgi();
    /* Ayarlar her seyden once yaziliyor: bir sey ters gittiginde ilk sorulan
       soru "hangi ayarlarla calisti" oluyor, ve o cevap hata mesajinin
       altinda kalmamali. */
    printf("  Port     : %d\n", g_port);
    wprintf(L"  Dagitim  : %ls\n", g_dagitim[0] ? g_dagitim : L"(varsayilan)");
    wprintf(L"  Klasor   : %ls\n", g_klasor);
    if (g_jeton[0] != L'\0') {
        /* Adres sabit: bir kez yer imine ekleyin, hep calisir. */
        wprintf(L"  Adres    : http://localhost:%d/?token=%ls\n", g_port, g_jeton);
        if (jeton_yeni)
            yaz("             (jeton uretildi ve jarvis.ini'ye kaydedildi;\n"
                "              bundan sonra hep ayni kalacak)\n");
    }
    cizgi();

    /* Zaten calisiyorsa ikinci kopya baslatma. */
    if (panel_hazir(g_port)) {
        printf("\n  Panel zaten calisiyor (port %d).\n", g_port);
        /* Baska bir pencerede baslatilmis olabilir; o zaman jetonunu
           bilmiyoruz. Sessizce jetonsuz adres acmak kullaniciyi panel yerine
           "jeton gerekli" sayfasina goturur — soylemek daha durust. */
        if (g_uzak_jeton_ister == 1 && !g_jeton_ayarlandi) {
            yaz("\n  ! Calisan panel jeton istiyor ve jetonu bu baslatici uretmedi.\n");
            yaz("    Paneli baslattiginiz penceredeki adresi kullanin,\n");
            yaz("    veya o pencereyi kapatip buradan yeniden baslatin.\n\n");
            yaz("    Kapatmak icin bir tusa basin.\n");
            (void)getchar();
            WSACleanup();
            return 4;
        }
        /* Calisan panel jeton istemiyorsa urettigimiz jetonu adrese
           koymanin anlami yok; adres sade kalsin. */
        if (g_uzak_jeton_ister == 0 && !g_jeton_ayarlandi) g_jeton[0] = L'\0';
        /* Ayarlar acilista okunuyor. Simgeye tekrar tiklamak calisan paneli
           yeniden BASLATMIYOR — .env'i degistirip "neden ayni" diye soran
           birinin ilk ihtiyaci bu cumle. */
        yaz("  (Ayar degistirdiyseniz once bu paneli KAPATIN: ayarlar\n");
        yaz("   yalnizca acilista okunuyor.)\n");
        yaz("  Tarayici aciliyor...\n");
        if (g_tarayici) tarayici_ac(g_port);
        Sleep(1500);
        WSACleanup();
        return 0;
    }

    if (g_mod == MOD_WINDOWS) {
        /* Windows modunda WSL aranmiyor. Aranan sey Python: yoksa panel
           baslamaz ve sebebi "CreateProcess hata 2"den okunmaz. */
        wchar_t python[512];
        if (g_python[0] != L'\0')
            wcsncpy(python, g_python, 511), python[511] = L'\0';
        else
            _snwprintf(python, 512, L"%ls\\.venv\\Scripts\\python.exe", g_klasor);
        if (!dosya_var(python)) {
            yaz("\n  ! Python bulunamadi.\n\n");
            wprintf(L"    Aranan: %ls\n\n", python);
            yaz("    Kurulum yarim kalmis olabilir. Kur.cmd'yi tekrar\n");
            yaz("    calistirin, ya da jarvis.ini icindeki 'python'\n");
            yaz("    satirina python.exe'nin tam yolunu yazin.\n\n");
            yaz("    Kapatmak icin bir tusa basin.\n");
            (void)getchar();
            WSACleanup();
            return 2;
        }
    } else {
        wchar_t wsl_yolu[MAX_PATH];
        if (!wsl_bulundu(wsl_yolu, MAX_PATH)) {
            yaz("\n  ! wsl.exe bulunamadi.\n\n");
            yaz("    Bu kurulum WSL2 icinde calisiyor. WSL kurulu degilse\n");
            yaz("    yonetici PowerShell'de: wsl --install\n\n");
            yaz("    Windows'a dogrudan kurmak icin jarvis.ini icinde\n");
            yaz("    mod = windows yapin.\n\n");
            yaz("    Kapatmak icin bir tusa basin.\n");
            (void)getchar();
            WSACleanup();
            return 2;
        }
    }

    yaz("\n  Durdurmak icin: bu pencereyi kapatin veya Ctrl-C\n");
    yaz("  Panel baslatiliyor (ilk acilis biraz surebilir)...\n\n");

    HANDLE is_parcacigi = CreateThread(NULL, 0, bekle_ve_ac, NULL, 0, NULL);

    wchar_t komut[4096];
    komut_kur(komut, 4096);

    STARTUPINFOW baslangic;
    PROCESS_INFORMATION surec;
    memset(&baslangic, 0, sizeof(baslangic));
    baslangic.cb = sizeof(baslangic);

    /* Konsolu devrediyoruz: panelin ciktisi bu pencerede aksin. */
    /* Calisma klasoru Windows modunda projenin kendisi: .env ORADAN
       okunuyor, ve baska bir klasorden baslatilan panel butun ayarlari
       gormeden aciliyor. WSL modunda betik zaten kendi 'cd'sini yapiyor. */
    const wchar_t *calisma = (g_mod == MOD_WINDOWS) ? g_klasor : NULL;
    BOOL tamam = CreateProcessW(NULL, komut, NULL, NULL, TRUE,
                                0, NULL, calisma, &baslangic, &surec);
    if (!tamam) {
        printf("\n  ! Panel baslatilamadi (hata %lu).\n\n", GetLastError());
        /* Calistirilmaya calisilan satiri gostermek, "neden olmadi"
           sorusunu tek bakista cevapliyor. Normalde yazilmiyor: calisirken
           gurultu, bozulunca ise ilk ihtiyac duyulan sey. */
        wprintf(L"    Denenen komut:\n    %ls\n\n", komut);
        yaz("    Kapatmak icin bir tusa basin.\n");
        (void)getchar();
        if (is_parcacigi) CloseHandle(is_parcacigi);
        WSACleanup();
        return 3;
    }

    WaitForSingleObject(surec.hProcess, INFINITE);

    DWORD cikis = 0;
    GetExitCodeProcess(surec.hProcess, &cikis);
    CloseHandle(surec.hProcess);
    CloseHandle(surec.hThread);
    if (is_parcacigi) CloseHandle(is_parcacigi);
    WSACleanup();

    if (cikis != 0) {
        yaz("\n  Panel kapandi. Sebebi yukarida yaziyor.\n");
        yaz("  Kapatmak icin bir tusa basin.\n");
        (void)getchar();
    }
    return (int)cikis;
}
