(() => {
  const form = document.getElementById("case-form");
  if (!form) return;

  const presets = window.THEVERUM_PRESETS || { conclusion: [], notable_features: [] };

  const fields = {
    brand: () => form.querySelector('[name="brand"]')?.value?.trim() || "бренд",
    model: () => form.querySelector('[name="model"]')?.value?.trim() || "модель",
    category: () => form.querySelector('[name="category"]')?.value?.trim() || "категория",
    color: () => form.querySelector('[name="color"]')?.value?.trim() || "цвет",
    material: () => form.querySelector('[name="material"]')?.value?.trim() || "материал",
    serial: () => form.querySelector('[name="serial_display"]')?.value?.trim() || "идентификатор",
    identifier: () => form.querySelector('[name="identifier_notes"]')?.value?.trim() || "",
  };

  function fillTemplate(text) {
    return text
      .replaceAll("{{brand}}", fields.brand())
      .replaceAll("{{model}}", fields.model())
      .replaceAll("{{category}}", fields.category())
      .replaceAll("{{color}}", fields.color())
      .replaceAll("{{material}}", fields.material())
      .replaceAll("{{serial}}", fields.serial())
      .replaceAll("{{identifier}}", fields.identifier());
  }

  function applyPreset(kind, selectEl, targetName) {
    const id = selectEl.value;
    if (!id) return;
    const item = (presets[kind] || []).find((p) => String(p.id) === String(id));
    if (!item) return;
    const target = form.querySelector(`[name="${targetName}"]`);
    if (!target) return;
    target.value = fillTemplate(item.body);
  }

  const conclusionSelect = document.getElementById("preset-conclusion");
  const featuresSelect = document.getElementById("preset-notable");
  if (conclusionSelect) {
    conclusionSelect.addEventListener("change", () =>
      applyPreset("conclusion", conclusionSelect, "conclusion")
    );
  }
  if (featuresSelect) {
    featuresSelect.addEventListener("change", () =>
      applyPreset("notable_features", featuresSelect, "notable_features")
    );
  }

  document.getElementById("refill-presets")?.addEventListener("click", (e) => {
    e.preventDefault();
    if (conclusionSelect?.value) applyPreset("conclusion", conclusionSelect, "conclusion");
    if (featuresSelect?.value) applyPreset("notable_features", featuresSelect, "notable_features");
  });
})();
