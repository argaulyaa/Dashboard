import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

// Context penghubung page aktif <-> TopBar sticky.
//
// Pola pakai:
//   * Page   : usePageHeader({ title, subtitle, right })
//              Mengisi header TopBar selama page hidup; otomatis dibersihkan
//              saat page unmount biar tidak stale antar route.
//   * TopBar : const { title, subtitle, right } = usePageHeader();
//              Tanpa argumen = baca header yang sedang diset page aktif.
//
// State dan setter sengaja dipisah jadi dua context: page yang MENULIS
// header cuma berlangganan setter (identitasnya stabil), jadi page tidak
// ikut ter-render ulang setiap kali isi header berubah - hanya TopBar
// (pembaca state) yang render ulang. Ini mencegah loop render.

const EMPTY_HEADER = { title: "", subtitle: "", right: null };

const PageHeaderStateContext = createContext(EMPTY_HEADER);
const PageHeaderSetContext = createContext(() => {});

export function PageHeaderProvider({ children }) {
  const [header, setHeader] = useState(EMPTY_HEADER);

  // Setter stabil (identitas tidak pernah berubah - aman jadi dependency).
  // null/undefined dinormalisasi balik ke bentuk kosong.
  const setPageHeader = useCallback((next) => {
    setHeader(next ?? EMPTY_HEADER);
  }, []);

  const stateValue = useMemo(() => header, [header]);

  return (
    <PageHeaderSetContext.Provider value={setPageHeader}>
      <PageHeaderStateContext.Provider value={stateValue}>
        {children}
      </PageHeaderStateContext.Provider>
    </PageHeaderSetContext.Provider>
  );
}

export function usePageHeader(config) {
  const header = useContext(PageHeaderStateContext);
  const setPageHeader = useContext(PageHeaderSetContext);

  // Mode SET dipanggil dengan objek config ({ title, subtitle, right }).
  //
  // PENTING (fix regresi blank-page): JANGAN panggil setPageHeader tiap
  // render dengan objek baru (efek tanpa dependency array). Objek config
  // literal baru tiap render + efek tanpa dep = setState tiap commit ->
  // "Maximum update depth exceeded" -> React berhenti memproses transisi
  // router -> halaman beku/blank diam-diam di build produksi.
  //
  // Solusi: jadikan FIELD config yang stabil sebagai dependency effect,
  // bukan objeknya. Efek hanya jalan saat isi header benar-benar berubah,
  // saat mount, atau saat unmount (cleanup mengosongkan header supaya
  // route berikutnya tidak membawa header lama). Identitas setPageHeader
  // stabil (useCallback []), jadi aman jadi dependency.
  const title = config === undefined ? undefined : (config.title ?? "");
  const subtitle = config === undefined ? undefined : (config.subtitle ?? "");
  const right = config === undefined ? undefined : (config.right ?? null);

  useEffect(() => {
    if (config === undefined) return undefined; // mode GET: no-op
    setPageHeader({ title, subtitle, right });
    return () => setPageHeader(null);
  }, [setPageHeader, title, subtitle, right]);

  // Mode GET: tanpa argumen, kembalikan header aktif (dipakai TopBar).
  if (config === undefined) return header;
  return undefined;
}
