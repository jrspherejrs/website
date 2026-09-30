const toggle = document.querySelector(".nav-toggle");
const navigation = document.querySelector("#primary-navigation");

if (toggle instanceof HTMLButtonElement && navigation instanceof HTMLElement) {
  const desktop = window.matchMedia("(min-width: 48rem)");

  const closeMenu = () => {
    toggle.setAttribute("aria-expanded", "false");
    navigation.hidden = true;
  };

  const syncMenu = () => {
    if (desktop.matches) {
      toggle.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      navigation.hidden = false;
      return;
    }

    toggle.hidden = false;
    closeMenu();
  };

  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    navigation.hidden = expanded;
  });

  navigation.addEventListener("click", (event) => {
    if (!desktop.matches && event.target instanceof HTMLAnchorElement) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      closeMenu();
      toggle.focus();
    }
  });

  if (typeof desktop.addEventListener === "function") {
    desktop.addEventListener("change", syncMenu);
  } else {
    desktop.addListener(syncMenu);
  }

  syncMenu();
}
