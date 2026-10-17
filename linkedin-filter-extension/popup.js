async function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function render() {
  const state = await send({ type: "SCOUT_LENS_GET_STATE" });
  document.querySelector("#status").textContent = state.paused
    ? "Escaneo pausado. No se abrirán nuevas páginas de detalle."
    : "Activo solo en LinkedIn Jobs. Los datos se guardan localmente.";
  document.querySelector("#jobs").textContent = `${state.jobLookups} / 12`;
  document.querySelector("#companies").textContent = `${state.companyLookups} / 8`;
  const pause = document.querySelector("#pause");
  pause.textContent = state.paused ? "Reanudar escaneo" : "Pausar escaneo";
  pause.onclick = async () => {
    await send({ type: "SCOUT_LENS_SET_PAUSED", paused: !state.paused });
    render();
  };
}

document.querySelector("#clear").addEventListener("click", async () => {
  await send({ type: "SCOUT_LENS_CLEAR_CACHE" });
  render();
});

render();
