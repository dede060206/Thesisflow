(function () {
  const dialog = document.getElementById("thesis-save-dialog");
  if (!dialog) return;
  const select = document.getElementById("thesis-save-select");
  const status = document.getElementById("thesis-save-status");
  const submit = document.getElementById("thesis-save-submit");
  let pendingPayload = null;

  window.ThesisflowSaveEvidence = async function (payload) {
    pendingPayload = payload;
    status.textContent = "正在加载 Thesis...";
    select.innerHTML = "";
    dialog.showModal();
    try {
      const response = await fetch("/api/theses");
      const theses = await response.json();
      if (!theses.length) {
        status.innerHTML = '还没有 Thesis。<a href="/theses/new">先创建一个</a>';
        submit.disabled = true;
        return;
      }
      theses.forEach((thesis) => {
        const option = document.createElement("option");
        option.value = thesis.id;
        option.textContent = thesis.title;
        select.appendChild(option);
      });
      submit.disabled = false;
      status.textContent = "选择要加入的 Thesis";
    } catch (error) {
      status.textContent = "无法加载 Thesis";
      submit.disabled = true;
    }
  };

  document.getElementById("thesis-save-cancel").addEventListener("click", () => {
    dialog.close();
  });

  submit.addEventListener("click", async () => {
    if (!pendingPayload || !select.value) return;
    submit.disabled = true;
    status.textContent = "保存中...";
    const response = await fetch(`/api/theses/${select.value}/evidence/import`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(pendingPayload)
    });
    const data = await response.json();
    if (!response.ok) {
      status.textContent = data.detail || "保存失败";
      submit.disabled = false;
      return;
    }
    status.innerHTML = `已保存。<a href="/theses/${select.value}">打开 Thesis</a>`;
  });
})();
