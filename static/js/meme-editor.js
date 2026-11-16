(() => {
  const form = document.getElementById("meme-editor-form");
  if (!form) return;

  const imageInput = document.getElementById("id_image");
  const editor = document.getElementById("meme-editor");
  const canvas = document.getElementById("meme-canvas");
  const context = canvas.getContext("2d");
  const blockList = document.getElementById("text-block-list");
  const contentInput = document.getElementById("text-block-content");
  const fontInput = document.getElementById("text-block-font");
  const sizeInput = document.getElementById("text-block-size");
  const sizeOutput = document.getElementById("text-size-value");
  const colorInput = document.getElementById("text-block-color");
  const addButton = document.getElementById("add-text-block");
  const deleteButton = document.getElementById("delete-text-block");
  const submitButton = document.getElementById("publish-meme");
  const captionInput = document.getElementById("id_caption");

  let sourceImage = null;
  let objectUrl = null;
  let blocks = [];
  let selectedBlock = -1;
  let dragging = false;
  let prepared = false;
  let generatedCaption = "";

  function syncCaption() {
    const text = blocks
      .map((block) => block.text.trim())
      .filter(Boolean)
      .join(" · ")
      .slice(0, 280);
    if (!captionInput.value.trim() || captionInput.value === generatedCaption) {
      captionInput.value = text;
    }
    generatedCaption = text;
  }

  function linesFor(block) {
    const fontSize = block.fontRatio * canvas.width;
    context.font = `700 ${fontSize}px "${block.font}"`;
    const maxWidth = canvas.width * 0.9;
    const lines = [];

    for (const paragraph of block.text.split("\n")) {
      const words = paragraph.split(/\s+/).filter(Boolean);
      if (!words.length) {
        lines.push("");
        continue;
      }

      let line = "";
      for (const word of words) {
        const candidate = line ? `${line} ${word}` : word;
        if (line && context.measureText(candidate).width > maxWidth) {
          lines.push(line);
          line = word;
        } else {
          line = candidate;
        }
      }
      lines.push(line);
    }

    return { lines, fontSize, maxWidth };
  }

  function draw(showSelection = true) {
    if (!sourceImage) return;

    canvas.width = sourceImage.naturalWidth;
    canvas.height = sourceImage.naturalHeight;
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(sourceImage, 0, 0);

    blocks.forEach((block, index) => {
      const { lines, fontSize, maxWidth } = linesFor(block);
      const lineHeight = fontSize * 1.16;
      const height = lineHeight * lines.length;
      const x = block.x * canvas.width;
      const y = block.y * canvas.height;

      context.font = `700 ${fontSize}px "${block.font}"`;
      const widestLine = Math.min(
        maxWidth,
        Math.max(0, ...lines.map((line) => context.measureText(line).width))
      );
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.lineJoin = "round";
      context.lineWidth = Math.max(3, fontSize * 0.18);
      context.strokeStyle = "rgba(0, 0, 0, 0.72)";
      context.fillStyle = block.color;

      lines.forEach((line, lineIndex) => {
        const lineY = y + (lineIndex - (lines.length - 1) / 2) * lineHeight;
        context.strokeText(line, x, lineY, maxWidth);
        context.fillText(line, x, lineY, maxWidth);
      });

      if (showSelection && index === selectedBlock) {
        const bounds = {
          left: x - widestLine / 2 - fontSize * 0.25,
          right: x + widestLine / 2 + fontSize * 0.25,
          top: y - height / 2 - fontSize * 0.25,
          bottom: y + height / 2 + fontSize * 0.25,
        };
        context.save();
        context.setLineDash([fontSize * 0.18, fontSize * 0.12]);
        context.lineWidth = Math.max(2, fontSize * 0.035);
        context.strokeStyle = "#d8ff72";
        context.strokeRect(
          bounds.left,
          bounds.top,
          bounds.right - bounds.left,
          bounds.bottom - bounds.top
        );
        context.restore();
        block.bounds = bounds;
      } else {
        block.bounds = {
          left: x - widestLine / 2 - fontSize * 0.25,
          right: x + widestLine / 2 + fontSize * 0.25,
          top: y - height / 2 - fontSize * 0.25,
          bottom: y + height / 2 + fontSize * 0.25,
        };
      }
    });
  }

  function updateBlockButtons() {
    blockList.replaceChildren();
    blocks.forEach((block, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `text-block-chip${index === selectedBlock ? " is-selected" : ""}`;
      button.textContent = block.text.trim().replace(/\s+/g, " ").slice(0, 24) || `Текст ${index + 1}`;
      button.addEventListener("click", () => selectBlock(index));
      blockList.append(button);
    });

    deleteButton.disabled = selectedBlock < 0;
  }

  function selectBlock(index) {
    selectedBlock = index;
    const block = blocks[index];
    if (block) {
      contentInput.value = block.text;
      fontInput.value = block.font;
      colorInput.value = block.color;
      updateSizeControl();
    } else {
      contentInput.value = "";
    }
    updateBlockButtons();
    draw();
  }

  function updateSizeControl() {
    if (selectedBlock < 0 || !sourceImage) return;
    const previewWidth = canvas.getBoundingClientRect().width;
    const previewSize = Math.round(blocks[selectedBlock].fontRatio * previewWidth);
    const displayedSize = Math.max(14, Math.min(84, previewSize));
    sizeInput.value = String(displayedSize);
    sizeOutput.value = `${displayedSize} px`;
  }

  function addBlock() {
    if (!sourceImage || blocks.length >= 8) return;
    const previewWidth = canvas.getBoundingClientRect().width || canvas.width;
    blocks.push({
      text: `Текст ${blocks.length + 1}`,
      font: "Impact",
      color: "#ffffff",
      fontRatio: Math.min(56 / previewWidth, 0.16),
      x: 0.5,
      y: 0.5,
      bounds: null,
    });
    selectBlock(blocks.length - 1);
    syncCaption();
    addButton.disabled = blocks.length >= 8;
  }

  function loadSelectedImage(file) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      window.alert("Обери зображення JPG, PNG або WebP.");
      imageInput.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      window.alert("Зображення має бути не більшим за 5 МБ.");
      imageInput.value = "";
      return;
    }

    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      if (image.naturalWidth * image.naturalHeight > 24000000) {
        window.alert("Зображення завелике. Максимальний розмір — 24 мегапікселі.");
        imageInput.value = "";
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
        return;
      }
      sourceImage = image;
      editor.hidden = false;
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      blocks = [];
      selectedBlock = -1;
      addBlock();
      draw();
    };
    image.onerror = () => {
      window.alert("Не вдалося відкрити це зображення. Спробуй інший файл.");
      imageInput.value = "";
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    };
    image.src = objectUrl;
  }

  function updateSelectedBlock() {
    if (selectedBlock < 0) return;
    blocks[selectedBlock].text = contentInput.value;
    blocks[selectedBlock].font = fontInput.value;
    blocks[selectedBlock].color = colorInput.value;
    syncCaption();
    updateBlockButtons();
    draw();
  }

  function canvasPoint(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
  }

  imageInput.addEventListener("change", () => loadSelectedImage(imageInput.files[0]));
  addButton.addEventListener("click", addBlock);
  deleteButton.addEventListener("click", () => {
    if (selectedBlock < 0) return;
    blocks.splice(selectedBlock, 1);
    selectBlock(blocks.length ? Math.min(selectedBlock, blocks.length - 1) : -1);
    addButton.disabled = blocks.length >= 8;
  });
  contentInput.addEventListener("input", updateSelectedBlock);
  fontInput.addEventListener("change", updateSelectedBlock);
  colorInput.addEventListener("input", updateSelectedBlock);
  sizeInput.addEventListener("input", () => {
    if (selectedBlock < 0 || !sourceImage) return;
    const previewWidth = canvas.getBoundingClientRect().width;
    blocks[selectedBlock].fontRatio = Number(sizeInput.value) / previewWidth;
    sizeOutput.value = `${sizeInput.value} px`;
    draw();
  });

  canvas.addEventListener("pointerdown", (event) => {
    if (!sourceImage) return;
    const point = canvasPoint(event);
    let blockIndex = -1;
    for (let index = blocks.length - 1; index >= 0; index -= 1) {
      const bounds = blocks[index].bounds;
      if (
        bounds &&
        point.x >= bounds.left &&
        point.x <= bounds.right &&
        point.y >= bounds.top &&
        point.y <= bounds.bottom
      ) {
        blockIndex = index;
        break;
      }
    }
    if (blockIndex < 0) return;
    selectBlock(blockIndex);
    dragging = true;
    canvas.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging || selectedBlock < 0) return;
    const point = canvasPoint(event);
    blocks[selectedBlock].x = Math.max(0, Math.min(1, point.x / canvas.width));
    blocks[selectedBlock].y = Math.max(0, Math.min(1, point.y / canvas.height));
    draw();
  });
  canvas.addEventListener("pointerup", () => {
    dragging = false;
  });
  canvas.addEventListener("pointercancel", () => {
    dragging = false;
  });

  function createBlob(quality, width, height) {
    return new Promise((resolve) => {
      const exportCanvas = document.createElement("canvas");
      exportCanvas.width = width;
      exportCanvas.height = height;
      const exportContext = exportCanvas.getContext("2d");
      exportContext.fillStyle = "#ffffff";
      exportContext.fillRect(0, 0, width, height);
      exportContext.drawImage(sourceImage, 0, 0, width, height);

      const scaleX = width / canvas.width;
      const scaleY = height / canvas.height;
      blocks.forEach((block) => {
        const { lines, fontSize, maxWidth } = linesFor(block);
        const scaledFontSize = fontSize * scaleX;
        const lineHeight = scaledFontSize * 1.16;
        const x = block.x * width;
        const y = block.y * height;

        exportContext.font = `700 ${scaledFontSize}px "${block.font}"`;
        exportContext.textAlign = "center";
        exportContext.textBaseline = "middle";
        exportContext.lineJoin = "round";
        exportContext.lineWidth = Math.max(3, scaledFontSize * 0.18);
        exportContext.strokeStyle = "rgba(0, 0, 0, 0.72)";
        exportContext.fillStyle = block.color;
        lines.forEach((line, lineIndex) => {
          const lineY = y + (lineIndex - (lines.length - 1) / 2) * lineHeight;
          exportContext.strokeText(line, x, lineY, maxWidth * scaleX);
          exportContext.fillText(line, x, lineY, maxWidth * scaleX);
        });
      });

      exportCanvas.toBlob(resolve, "image/jpeg", quality);
    });
  }

  async function renderFinalImage() {
    let width = canvas.width;
    let height = canvas.height;
    for (let scale = 1; scale >= 0.5; scale *= 0.85) {
      for (const quality of [0.9, 0.8, 0.7]) {
        const blob = await createBlob(
          quality,
          Math.max(1, Math.round(width * scale)),
          Math.max(1, Math.round(height * scale))
        );
        if (blob && blob.size <= 5 * 1024 * 1024) return blob;
      }
    }
    throw new Error("Не вдалося зменшити зображення до 5 МБ.");
  }

  form.addEventListener("submit", async (event) => {
    if (prepared || !sourceImage) return;
    event.preventDefault();

    syncCaption();
    if (!captionInput.value.trim()) {
      window.alert("Додай текст до мему або заповни підпис роботи.");
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Готуємо мем…";
    try {
      const blob = await renderFinalImage();
      const finalFile = new File([blob], "meme.jpg", { type: "image/jpeg" });
      const transfer = new DataTransfer();
      transfer.items.add(finalFile);
      imageInput.files = transfer.files;
      prepared = true;
      form.requestSubmit(submitButton);
    } catch (error) {
      window.alert(error.message || "Не вдалося підготувати зображення.");
      submitButton.disabled = false;
      submitButton.textContent = "Опублікувати мем ↗";
    }
  });

  window.addEventListener("resize", updateSizeControl);
})();
