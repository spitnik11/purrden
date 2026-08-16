import "pixi.js/unsafe-eval";
import "./style.css";
import { startApp } from "./ui/app";

const root = document.querySelector<HTMLElement>("#app");
if (!root) throw new Error("#app missing");

startApp(root).catch((err) => {
  root.innerHTML = `<pre style="color:#ef7d57;padding:1rem">Failed to start Purrden:\n${
    err instanceof Error ? err.stack ?? err.message : String(err)
  }</pre>`;
  console.error(err);
});
