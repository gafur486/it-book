const App = (() => {
  const LS_THEME = "itbook_theme";
  const LS_LANG = "itbook_lang";
  const LS_ACCENT = "itbook_accent";

  const dict = {
    tj: {
      books: "Китобҳо",
      wiki: "Wiki",
      settings: "Settings",
      search: "Ҷустуҷӯ",
      allGrades: "Ҳама синфҳо",
      noBooks: "Ҳоло китоб нест.",
      openPdf: "Кушодани PDF",
      theme: "Мавзӯъ",
      themeDesc: "Рӯз/Шаб",
      light: "Сафед",
      dark: "Торик",
      language: "Забон",
      accent: "Ранги панел",
      apply: "Apply",
    },
    ru: {
      books: "Книги",
      wiki: "Вики",
      settings: "Настройки",
      search: "Поиск",
      allGrades: "Все классы",
      noBooks: "Пока нет книг.",
      openPdf: "Открыть PDF",
      theme: "Тема",
      themeDesc: "День/Ночь",
      light: "Светлая",
      dark: "Тёмная",
      language: "Язык",
      accent: "Цвет панели",
      apply: "Применить",
    },
    en: {
      books: "Books",
      wiki: "Wiki",
      settings: "Settings",
      search: "Search",
      allGrades: "All grades",
      noBooks: "No books yet.",
      openPdf: "Open PDF",
      theme: "Theme",
      themeDesc: "Light/Dark",
      light: "Light",
      dark: "Dark",
      language: "Language",
      accent: "Panel color",
      apply: "Apply",
    }
  };

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(LS_THEME, theme);
  }

  function setLang(lang) {
    localStorage.setItem(LS_LANG, lang);
    applyI18n();
  }

  function setAccent(hex) {
    document.documentElement.style.setProperty("--accent", hex);
    localStorage.setItem(LS_ACCENT, hex);
  }

  function applyI18n() {
    const lang = localStorage.getItem(LS_LANG) || "tj";
    const d = dict[lang] || dict.tj;
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const k = el.getAttribute("data-i18n");
      if (d[k]) el.textContent = d[k];
    });
  }

  function init() {
    const theme = localStorage.getItem(LS_THEME) || "light";
    setTheme(theme);

    const accent = localStorage.getItem(LS_ACCENT);
    if (accent) setAccent(accent);

    const picker = document.getElementById("accentPicker");
    if (picker) {
      picker.value = accent || "#2563eb";
    }

    applyI18n();
  }

  function applyAccentFromPicker() {
    const picker = document.getElementById("accentPicker");
    if (picker) setAccent(picker.value);
  }

  return { init, setTheme, setLang, applyAccentFromPicker };
})();

window.addEventListener("DOMContentLoaded", App.init);
window.App = App;