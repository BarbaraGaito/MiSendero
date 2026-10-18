"use strict";
(() => {
  let token = null;
  const byId = (id) => document.getElementById(id);
  const status = (message) => { byId("status").textContent = message; };
  const api = async (path, method = "GET", body) => {
    const response = await fetch(`/api${path.startsWith("/reports") ? "" : "/auth"}${path}`, { method, headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { "Content-Type": "application/json" } : {}),
    }, body: body ? JSON.stringify(body) : undefined, cache: "no-store", redirect: "error" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "No se pudo completar la solicitud");
    return data;
  };
  byId("account-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const password = byId("password").value;
      byId("password").value = "";
      const login = await api("/login", "POST", { email: byId("email").value, password });
      token = login.token;
      byId("name").value = login.user.name;
      byId("password").value = "";
      byId("actions").hidden = false;
      byId("moderation").hidden = login.user.role !== "admin";
      status("Cuenta verificada. Podés gestionar tus datos durante esta visita.");
    } catch (error) { token = null; byId("password").value = ""; byId("actions").hidden = true; byId("moderation").hidden = true; byId("flags").replaceChildren(); status(error.message); }
  });
  byId("export").addEventListener("click", async () => {
    try {
      const data = await api("/me/data");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = "misendero-mis-datos.json"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status("Descargados los datos de la API. Los datos exclusivamente locales se gestionan desde la app.");
    } catch (error) { status(error.message); }
  });
  byId("name-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await api("/me", "PATCH", { name: byId("name").value }); status("Nombre actualizado."); }
    catch (error) { status(error.message); }
  });
  byId("delete").addEventListener("click", async () => {
    if (!byId("confirm").checked) return status("Marcá la confirmación de eliminación para continuar.");
    if (!byId("delete-password").value) return status("Volvé a ingresar la contraseña para confirmar la baja.");
    byId("delete").disabled = true;
    try {
      const password = byId("delete-password").value;
      byId("delete-password").value = "";
      await api("/me", "DELETE", { password });
      token = null;
      byId("actions").hidden = true;
      byId("moderation").hidden = true;
      byId("flags").replaceChildren();
      status("Cuenta y datos remotos eliminados. Abrí las otras instalaciones con conexión para limpiar sus datos locales.");
    } catch (error) { status(error.message); }
    finally { byId("delete").disabled = false; }
  });
  fetch("/api/privacy-contact", { cache: "no-store" }).then((r) => r.json()).then((data) => {
    if (data.url) { byId("contact").href = data.url; byId("contact").hidden = false; }
  }).catch(() => {});
  byId("refresh-moderation").addEventListener("click", async () => {
    try {
      const flags = await api("/reports/moderation");
      byId("flags").replaceChildren();
      for (const flag of flags) {
        const item = document.createElement("article");
        const text = document.createElement("p");
        text.textContent = `${flag.issue_summary}: ${flag.details || ""}. Denuncia: ${flag.reason}. Estado: ${flag.moderation_status}`;
        const button = document.createElement("button");
        const next = flag.moderation_status === "hidden" ? "visible" : "hidden";
        button.textContent = next === "hidden" ? "Ocultar reporte" : "Restaurar reporte";
        button.addEventListener("click", async () => {
          button.disabled = true;
          try { await api(`/reports/${flag.report_id}/moderate`, "POST", { status: next }); status("Moderación aplicada. Actualizá la lista para ver el estado."); }
          catch (error) { status(error.message); button.disabled = false; }
        });
        item.append(text, button); byId("flags").append(item);
      }
      if (!flags.length) status("No hay denuncias registradas.");
    } catch (error) { status(error.message); }
  });
  byId("sign-out").addEventListener("click", async () => {
    let confirmed = false;
    try { await api("/logout", "POST"); confirmed = true; } catch { /* Explain residual access below. */ }
    token = null; byId("delete-password").value = "";
    byId("account-form").reset(); byId("name-form").reset(); byId("confirm").checked = false;
    byId("actions").hidden = true; byId("moderation").hidden = true; byId("flags").replaceChildren();
    status(confirmed ? "Sesión web cerrada y revocada." : "Sesión web cerrada localmente. No se confirmó revocación; la credencial podría seguir vigente hasta vencer.");
  });
})();
