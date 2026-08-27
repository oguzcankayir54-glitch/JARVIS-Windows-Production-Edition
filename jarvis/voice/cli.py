"""``jarvis-ses`` — verify the ElevenLabs setup and speak text.

Run this right after putting the key in ``.env``: it confirms the credentials
work before voice is wired into a conversation, so a failure points at the
configuration rather than hiding inside the agent loop.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ..config import load_config
from .tts import (ElevenLabsTTS, TTSError, find_player, play_stream, save_stream,
                  tts_from_config)


#: ElevenLabs anahtarları bu uzunlukta olur (API'nin kendi doğrulaması).
_ELEVENLABS_KEY_LEN = 51


def _key_health(key: str) -> list[str]:
    """Report anything suspicious about the key without revealing it.

    A key pasted through an editor can pick up a stray space, a carriage
    return, or a smart quote — invisible on screen, but enough to make the
    API reject the request.
    """
    problems = []
    if key != key.strip():
        problems.append("başında/sonunda boşluk var")
    if not key.isascii():
        bad = {ch for ch in key if not ch.isascii()}
        problems.append(f"ASCII olmayan karakter içeriyor: {sorted(bad)!r}")
    if any(ch.isspace() for ch in key):
        problems.append("içinde boşluk/satır sonu var")
    if any(ord(ch) < 32 for ch in key):
        problems.append("görünmez kontrol karakteri içeriyor")
    if key.startswith(("'", '"')) or key.endswith(("'", '"')):
        problems.append("tırnak işareti içeriyor (gerekmez)")
    # ElevenLabs anahtarları sabit uzunlukta; API'nin kendi hata mesajı bunu
    # söylüyor, o yüzden isteğe çıkmadan burada yakalanabilir.
    clean = key.strip()
    if not clean:
        return problems

    # Bu denetimlerin hepsi "sk_" gecen degerlere bagli. Eski ElevenLabs
    # anahtarlarinda bu onek yoktu, ve tanimadigimiz bir bicime uzunluk
    # dayatmak gecerli bir anahtari yanlis yere suclamak olur.
    if "sk_" not in clean:
        return problems

    # Onek uzunluktan ayri bir isaret: icinde sk_ var ama onunla baslamiyorsa
    # basina bir sey yapismis demektir (cogunlukla satirin tamami
    # "ELEVENLABS_API_KEY=sk_..." diye yapistirilmis).
    if not clean.startswith("sk_"):
        problems.append("'sk_' ile başlamıyor — anahtarın kendisi değil, "
                        "satırın tamamı yapıştırılmış olabilir.")
    if len(clean) != _ELEVENLABS_KEY_LEN:
        problems.append(f"uzunluk {len(clean)} — beklenen {_ELEVENLABS_KEY_LEN}.")
        problems.extend(_length_diagnosis(clean, len(clean) - _ELEVENLABS_KEY_LEN))
    return problems


#: ElevenLabs anahtarı: "sk_" + 48 onaltılık karakter.
_KEY_SHAPE = re.compile(r"^sk_[0-9a-fA-F]{48}$")


def _length_diagnosis(clean: str, fazla: int) -> list[str]:
    """Say *what* is wrong with the length, not just that it is wrong.

    "Anahtarı yeniden kopyalayın" is what you tell someone once. When the
    same paste goes wrong twice, they need to know which end is wrong and by
    how much. Nothing here prints the key: only its shape and lengths.
    """
    if fazla < 0:
        return [f"{-fazla} karakter eksik — kopyalarken anahtarın başı veya "
                "sonu kesilmiş olabilir."]

    if clean.count("sk_") > 1:
        return ["içinde birden fazla 'sk_' var — anahtar iki kez yapıştırılmış "
                "görünüyor. Satırda tek bir anahtar kalmalı."]

    # En sık durum: gecerli anahtarin ardina fazladan metin yapismis.
    if _KEY_SHAPE.match(clean[:_ELEVENLABS_KEY_LEN]):
        return [f"ilk {_ELEVENLABS_KEY_LEN} karakter geçerli bir anahtar biçiminde; "
                f"SONDAKİ {fazla} karakter fazla.",
                f"Düzeltmek için: satırın sonundan {fazla} karakter silin."]

    # Bazen de basa bir sey yapisiyor (etiket, eski deger kalintisi).
    son = clean[-_ELEVENLABS_KEY_LEN:]
    if _KEY_SHAPE.match(son):
        return [f"son {_ELEVENLABS_KEY_LEN} karakter geçerli bir anahtar biçiminde; "
                f"BAŞTAKİ {fazla} karakter fazla.",
                f"Düzeltmek için: 'sk_' ile başlayan yerden öncesini silin."]

    return [f"{fazla} fazla karakter var ama anahtarın neresinde olduğu "
            "anlaşılamadı; satırı tamamen silip anahtarı yeniden yapıştırın."]


def _aktif_saglayici(cfg) -> str:
    """Which provider this configuration actually resolves to.

    Mirrors :func:`jarvis.voice.tts.build_tts`. If the two ever disagree this
    command reports on a provider that is not the one speaking, which is worse
    than not reporting at all.
    """
    secim = (cfg.tts_provider or "").strip().lower()
    if secim:
        return secim
    if cfg.voice_configured:
        return "elevenlabs"
    from .edge import edge_hazir
    return "piper" if edge_hazir() else "edge"


def _cmd_edge_kur(cfg) -> int:
    """Switch to the free Edge voice and prove it works before saying so."""
    from .edge import EdgeTTS, edge_hazir

    print("Edge sesi  (ücretsiz · anahtarsız · çevrimiçi)")
    eksik = edge_hazir()
    if eksik:
        print(f"\n✗ {eksik}")
        return 1

    # Yazmadan ÖNCE bak: yazdıktan sonra her klasör proje kökü gibi görünür.
    kokte = _proje_kokunde_mi()

    ses = cfg.edge_voice or "tr-TR-AhmetNeural"
    print(f"  Ses : {ses}")
    print("\n  Deneme sesi üretiliyor…", flush=True)
    tts = EdgeTTS(ses, speed=cfg.elevenlabs_speed, ca_bundle=cfg.edge_ca)
    try:
        ham = b"".join(tts.synthesize(
            "Sistem hazır efendim. BIOS ve SSD kontrolleri tamamlandı."))
    except TTSError as exc:
        print(f"\n✗ {exc}")
        return 1
    print(f"\n✓ Çalışıyor — {len(ham)} bayt üretildi.")

    # Ayari biz yaziyoruz. Bu adim iki kez kullaniciya birakildi ve iki kez
    # "ses hala ElevenLabs" diye geri geldi.
    yazildi = _env_ayarla("JARVIS_TTS_PROVIDER", "edge")
    if yazildi:
        print(f"✓ {yazildi} içine JARVIS_TTS_PROVIDER=edge yazıldı.")
        _env_ayarla("JARVIS_EDGE_VOICE", ses)
        _koke_dair_uyari(kokte)
    else:
        print("! .env yazılamadı. Elle ekleyin:  JARVIS_TTS_PROVIDER=edge")

    print()
    print("· Bu ses ÇEVRİMİÇİ: seslendirilecek metin Microsoft'a gidiyor.")
    print("  Her şeyin makinede kalmasını isterseniz:  jarvis-ses --piper-kur")
    print()
    print("✓ Denemek için:  jarvis-ses \"Merhaba efendim.\"")
    print("  Paneli AÇIKSA kapatıp yeniden başlatın: ayarlar açılışta okunuyor.")
    return 0


def _cmd_edge_sesler(cfg) -> int:
    from .edge import edge_hazir, sesler

    eksik = edge_hazir()
    if eksik:
        print(f"✗ {eksik}")
        return 1
    liste = sesler("tr")
    print(f"Türkçe Edge sesleri ({len(liste)}):\n")
    for ad, cinsiyet in liste:
        isaret = "→" if ad == cfg.edge_voice else " "
        print(f" {isaret} {ad:<24} {cinsiyet}")
    print("\nSeçtiğinizi .env içine JARVIS_EDGE_VOICE olarak yazın.")
    return 0


def _cmd_check_edge(cfg) -> int:
    from .edge import EdgeTTS, edge_hazir

    print("Edge ses yapılandırması  (ücretsiz · anahtarsız · çevrimiçi)")
    print(f"  Ses : {cfg.edge_voice}")
    print(f"  Hız : {cfg.elevenlabs_speed}")
    eksik = edge_hazir()
    if eksik:
        print(f"\n✗ {eksik}")
        return 1

    print("\n  Microsoft konuşma servisine bağlanılıyor…", flush=True)
    tts = EdgeTTS(cfg.edge_voice, speed=cfg.elevenlabs_speed, ca_bundle=cfg.edge_ca)
    try:
        ham = b"".join(tts.synthesize("Sistem hazır efendim."))
    except TTSError as exc:
        print(f"\n✗ {exc}")
        return 1
    print(f"\n✓ Çalışıyor — {len(ham)} bayt MP3 üretildi.")
    print("✓ Kota yok, anahtar yok.")
    print("· Seslendirilen metin Microsoft'a gidiyor; tamamen yerel ses için")
    print("  JARVIS_TTS_PROVIDER=piper.")

    player = find_player()
    if player:
        print(f"✓ Ses oynatıcı bulundu: {player[0]}")
    else:
        print("· Ses oynatıcı yok (ffplay/mpv) — panelde sesi tarayıcı çalar.")
    return 0


def _cmd_piper_kur(cfg) -> int:
    """Download the Piper voice model into the data directory."""
    import urllib.error
    import urllib.request

    from .piper import indirme_yolu, ses_klasoru

    kokte = _proje_kokunde_mi()   # yazmadan önce; gerekçe _koke_dair_uyari'de
    ses = cfg.piper_voice or "tr_TR-dfki-medium"
    klasor = ses_klasoru(cfg.data_dir)
    klasor.mkdir(parents=True, exist_ok=True)
    kok = indirme_yolu(ses)

    print(f"Piper sesi indiriliyor: {ses}")
    print(f"  Hedef: {klasor}")
    for ad in (f"{ses}.onnx", f"{ses}.onnx.json"):
        hedef = klasor / ad
        if hedef.is_file() and hedef.stat().st_size > 0:
            print(f"  = {ad} zaten var ({hedef.stat().st_size} bayt)")
            continue
        url = f"{kok}/{ad}?download=true"
        print(f"  ↓ {ad} …", end="", flush=True)
        try:
            # Gecici ada indirip sonra tasiyoruz: yarim kalan bir indirme
            # "model var" gibi gorunup ilk seslendirmede patlardi.
            gecici = hedef.with_suffix(hedef.suffix + ".yarim")
            with urllib.request.urlopen(url, timeout=120) as cevap, \
                    open(gecici, "wb") as dosya:
                while True:
                    parca = cevap.read(1 << 16)
                    if not parca:
                        break
                    dosya.write(parca)
            gecici.replace(hedef)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f" olmadı: {exc}")
            print("  İnternet bağlantısını kontrol edip tekrar deneyin.")
            return 1
        print(f" {hedef.stat().st_size} bayt")

    # Ayari elle yazdirmak yerine biz yaziyoruz. Bu adim iki kez atlandi ve
    # her seferinde "ses hala ElevenLabs" olarak geri geldi: modeli indirip
    # ayari acik birakmak, isin yarisini kullaniciya birakmak demek.
    print()
    yazildi = _env_ayarla("JARVIS_TTS_PROVIDER", "piper")
    if yazildi:
        print(f"✓ {yazildi} içine JARVIS_TTS_PROVIDER=piper yazıldı.")
        _koke_dair_uyari(kokte)
    else:
        print("! .env yazılamadı. Elle ekleyin:  JARVIS_TTS_PROVIDER=piper")

    print()
    print("✓ Ses hazır. Denemek için:  jarvis-ses \"Merhaba efendim.\"")
    print("  Paneli AÇIKSA kapatıp yeniden başlatın: ayarlar açılışta okunuyor.")
    return 0


def _proje_kokunde_mi() -> bool:
    """Whether this is the folder the panel will read its ``.env`` from.

    ``load_config`` reads ``Path.cwd()/.env``, and the launcher starts the
    panel with ``cd ~/jarvis``. So a setting written from anywhere else lands
    in a file nothing opens — and the symptom is "I changed it and the voice
    is still the same", which has already cost two rounds here.
    """
    from pathlib import Path

    simdi = Path.cwd()
    return (simdi / "pyproject.toml").is_file() or (simdi / ".env").is_file()


def _koke_dair_uyari(kokte: bool) -> None:
    """Warn when the setting was written where nothing will read it.

    Takes the answer as an argument rather than checking here: by the time
    this is printed the ``.env`` has just been created, which would make any
    folder look like the right one.
    """
    if kokte:
        return
    from pathlib import Path

    print()
    print(f"! Bu klasör proje kökü değil: {Path.cwd()}")
    print("  Panel ayarları BAŞLATILDIĞI klasördeki .env dosyasından okuyor,")
    print("  ve panel ~/jarvis içinde başlıyor. Buraya yazılan ayar okunmaz.")
    print("  Doğrusu:  cd ~/jarvis  ve komutu orada tekrarlayın.")


def _env_ayarla(anahtar: str, deger: str) -> str:
    """Set one key in the local ``.env``, preserving everything else.

    Returns the file path on success, empty string otherwise. Rewrites the
    file rather than appending: a second line with the same key would make
    the effective value depend on read order, which is exactly the kind of
    thing nobody finds when the setting "does not work".
    """
    from pathlib import Path

    yol = Path.cwd() / ".env"
    try:
        satirlar = (yol.read_text(encoding="utf-8-sig").splitlines()
                    if yol.is_file() else [])
        yeni, bulundu = [], False
        for satir in satirlar:
            kirpik = satir.strip()
            if not kirpik.startswith("#") and kirpik.split("=", 1)[0].strip() == anahtar:
                if not bulundu:
                    yeni.append(f"{anahtar}={deger}")
                    bulundu = True
                continue          # varsa fazlalik kopyalari at
            yeni.append(satir)
        if not bulundu:
            if yeni and yeni[-1].strip():
                yeni.append("")
            yeni.append(f"{anahtar}={deger}")
        yol.write_text("\n".join(yeni) + "\n", encoding="utf-8")
        return str(yol)
    except OSError:
        return ""


def _cmd_check_piper(cfg) -> int:
    from .piper import PiperTTS, piper_modeli

    model = piper_modeli(cfg.piper_voice, cfg.data_dir)
    print("Piper yapılandırması  (ücretsiz · yerel · kotasız)")
    print(f"  Ses          : {cfg.piper_voice}")
    print(f"  Model        : {model}")
    print(f"  Çalıştırıcı  : {cfg.piper_binary}")
    print(f"  GPU          : {'açık' if cfg.piper_cuda else 'kapalı (CPU)'}")

    tts = PiperTTS(model, binary=cfg.piper_binary,
                   speed=cfg.elevenlabs_speed, cuda=cfg.piper_cuda)
    print("\n  Deneme sesi üretiliyor…", flush=True)
    try:
        ham = b"".join(tts.synthesize("Sistem hazır efendim."))
    except TTSError as exc:
        print(f"\n✗ {exc}")
        return 1
    print(f"\n✓ Çalışıyor — {len(ham)} bayt WAV üretildi.")
    print("✓ Kota yok: istediğiniz kadar konuşabilir.")

    player = find_player()
    if player:
        print(f"✓ Ses oynatıcı bulundu: {player[0]}")
    else:
        print("· Ses oynatıcı yok (ffplay/mpv) — panelde sesi tarayıcı çalar.")
    return 0


def _cmd_check(cfg) -> int:
    saglayici = _aktif_saglayici(cfg)
    if saglayici == "piper":
        return _cmd_check_piper(cfg)
    if saglayici in ("edge", "microsoft", "edge-tts"):
        return _cmd_check_edge(cfg)
    if saglayici in ("yok", "kapali", "none", "off"):
        print("· Ses kapalı (JARVIS_TTS_PROVIDER=yok).")
        print("  Açmak için:  jarvis-ses --edge-kur   (ücretsiz)")
        return 0
    if saglayici not in ("elevenlabs", "11labs"):
        print(f"✗ Bilinmeyen sağlayıcı: {cfg.tts_provider}")
        print("  Seçenekler: edge | piper | elevenlabs | yok")
        return 1
    print("ElevenLabs yapılandırması")
    print(f"  API anahtarı : {cfg.masked_key()}")
    print(f"  Voice ID     : {cfg.elevenlabs_voice_id or '(yok)'}")
    print(f"  Model        : {cfg.elevenlabs_model_id}")
    print(f"  Format       : {cfg.elevenlabs_output_format}")
    print(f"  Dil          : {cfg.elevenlabs_language_code or 'otomatik'}")

    problems = _key_health(cfg.elevenlabs_api_key or "")
    if problems:
        print("\n⚠ Anahtarda sorun görünüyor:")
        for p in problems:
            print(f"    · {p}")
        print("  Anahtarı .env içine yeniden yapıştırın; tırnak veya boşluk olmasın.")

    if not cfg.voice_configured:
        print("\n✗ Eksik ayar. .env dosyanıza şunları ekleyin:")
        print("    ELEVENLABS_API_KEY=sk_...")
        print("    ELEVENLABS_VOICE_ID=...")
        return 1

    # Bounded so a slow answer fails with a message instead of looking frozen.
    tts = ElevenLabsTTS(
        cfg.elevenlabs_api_key, cfg.elevenlabs_voice_id, cfg.elevenlabs_model_id,
        timeout=min(20.0, cfg.elevenlabs_timeout), speed=cfg.elevenlabs_speed,
        output_format=cfg.elevenlabs_output_format,
        language_code=cfg.elevenlabs_language_code,
        stability=cfg.elevenlabs_stability,
        similarity_boost=cfg.elevenlabs_similarity_boost,
        style=cfg.elevenlabs_style, speaker_boost=cfg.elevenlabs_speaker_boost,
        max_retries=cfg.elevenlabs_max_retries,
    )
    print("\n  ElevenLabs'e bağlanılıyor…", flush=True)
    try:
        # Asking for the configured voice settles both questions in one small
        # request: a bad key answers 401, a wrong id answers 404.
        bilgi = tts.voice_info(cfg.elevenlabs_voice_id)
    except TTSError as exc:
        print(f"\n✗ {exc}")
        return 1

    print(f"\n✓ Anahtar geçerli.")
    print(f"✓ Voice ID eşleşti: {bilgi['name'] or '(isimsiz)'}")

    # A valid key with no credits left fails exactly like an invalid one, so
    # the number is worth seeing here rather than mid-conversation.
    kota = tts.quota()
    if kota is None:
        print("· Kota okunamadı (anahtarın bu yetkisi olmayabilir) — sorun değil.")
    elif kota["left"] == 0:
        print(f"\n✗ Krediniz bitti: {kota['used']}/{kota['limit']} karakter kullanılmış.")
        print("  Anahtar geçerli ama kota yenilenene kadar ses üretilemez.")
        return 1
    else:
        pay = kota["left"] / kota["limit"] if kota["limit"] else 0
        isaret = "!" if pay < 0.1 else "✓"
        print(f"{isaret} Kota: {kota['left']} / {kota['limit']} karakter kaldı"
              + (f" ({kota['tier']})" if kota["tier"] else ""))
        if pay < 0.1:
            print("  Az kaldı; uzun bir oturum ortasında bitebilir.")

    player = find_player()
    if player:
        print(f"✓ Ses oynatıcı bulundu: {player[0]}")
    else:
        # Only the terminal needs a player; in the panel the browser plays the
        # audio. Saying so keeps this from looking like a blocker.
        print("· Ses oynatıcı yok (ffplay/mpv/mpg123) — yalnızca terminalden")
        print("  dinlemek için gerekir. Panelde sesi tarayıcı çalar.")
        print("  İsterseniz:  sudo apt install ffmpeg")
        print("  Ya da dosyaya üretin:  jarvis-ses --kaydet deneme.mp3 \"metin\"")
    return 0


def _cmd_voices(cfg) -> int:
    if not cfg.elevenlabs_api_key:
        print("✗ ELEVENLABS_API_KEY ayarlı değil.")
        return 1
    tts = ElevenLabsTTS(cfg.elevenlabs_api_key, cfg.elevenlabs_voice_id or "x",
                        cfg.elevenlabs_model_id, timeout=20.0)
    print("ElevenLabs'e bağlanılıyor…", flush=True)
    try:
        voices = tts.voices()
    except TTSError as exc:
        print(f"✗ {exc}")
        return 1
    print(f"\nHesabınızdaki sesler ({len(voices)}):\n")
    for v in voices:
        işaret = "→" if v["voice_id"] == cfg.elevenlabs_voice_id else " "
        print(f" {işaret} {v['name']:<28} {v['voice_id']}")
    print("\nKullanmak istediğiniz kimliği .env içine ELEVENLABS_VOICE_ID olarak yazın.")
    return 0


def _cmd_speak(cfg, text: str, save_to: str | None) -> int:
    tts = tts_from_config(cfg)
    if not tts.available:
        print("✗ Ses yapılandırılmamış. Önce: jarvis-ses --kontrol")
        return 1
    try:
        if save_to:
            path = save_stream(tts.synthesize(text), save_to)
            print(f"✓ Kaydedildi: {path} ({path.stat().st_size} bayt)")
            return 0
        if not play_stream(tts.synthesize(text)):
            fallback = Path.cwd() / "jarvis-ses.mp3"
            save_stream(tts.synthesize(text), fallback)
            print(f"! Ses oynatıcı bulunamadı; dosyaya kaydedildi: {fallback}")
            print("  Oynatıcı için:  sudo apt install ffmpeg")
            return 0
        print("✓ Oynatıldı.")
        return 0
    except TTSError as exc:
        print(f"✗ {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-ses", description="ElevenLabs ses ayarlarını doğrula ve metni seslendir."
    )
    parser.add_argument("metin", nargs="?", help="Seslendirilecek metin")
    parser.add_argument("--kontrol", action="store_true", help="Anahtar ve Voice ID'yi doğrula")
    parser.add_argument("--sesler", action="store_true", help="Hesaptaki sesleri listele")
    parser.add_argument("--edge-kur", action="store_true",
                        help="Ücretsiz Edge sesine geç (önerilen)")
    parser.add_argument("--edge-sesler", action="store_true",
                        help="Türkçe Edge seslerini listele")
    parser.add_argument("--piper-kur", action="store_true",
                        help="Ücretsiz YEREL Piper sesini indir (çevrimdışı)")
    parser.add_argument("--kaydet", metavar="DOSYA", help="Oynatmak yerine MP3 olarak kaydet")
    args = parser.parse_args(argv)

    cfg = load_config()

    if args.edge_kur:
        return _cmd_edge_kur(cfg)
    if args.edge_sesler:
        return _cmd_edge_sesler(cfg)
    if args.piper_kur:
        return _cmd_piper_kur(cfg)
    if args.kontrol:
        return _cmd_check(cfg)
    if args.sesler:
        return _cmd_voices(cfg)
    if args.metin:
        return _cmd_speak(cfg, args.metin, args.kaydet)

    # No arguments: a check is the most useful default.
    return _cmd_check(cfg)


if __name__ == "__main__":
    sys.exit(main())
