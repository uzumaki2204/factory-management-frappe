(() => {
  'use strict';
  const picker = document.getElementById('service');
  const status = document.getElementById('status');
  const download = document.getElementById('download');
  const labels = document.body.dataset;
  let currentSpec = null;
  let currentKey = '';
  let requestNumber = 0;
  let availableServices = [];

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle('error', isError);
  }

  async function call(method, args = {}) {
    const url = new URL(`/api/method/factory_management.api_docs.${method}`, location.origin);
    for (const [key, value] of Object.entries(args)) url.searchParams.set(key, value);
    const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error();
    const result = await response.json();
    if (!Object.hasOwn(result, 'message')) throw new Error();
    return result.message;
  }

  async function showService(key) {
    const number = ++requestNumber;
    currentSpec = null;
    download.disabled = true;
    setStatus(labels.loading);
    try {
      const selected = availableServices.find(item => item.key === key);
      let spec;
      if (selected && selected.openapiUrl) {
        const source = new URL(selected.openapiUrl);
        const response = await fetch(source, { credentials: source.origin === location.origin ? 'same-origin' : 'omit' });
        if (!response.ok) throw new Error();
        spec = await response.json();
      } else {
        spec = await call('openapi', { service: key });
      }
      if (number !== requestNumber) return;
      currentSpec = spec;
      currentKey = key;
      setStatus('');
      const firstServer = spec.servers?.[0]?.url;
      const displaySpec = !selected?.openapiUrl && firstServer &&
        new URL(firstServer, location.origin).host === location.host
        ? { ...spec, servers: [{ ...spec.servers[0], url: location.origin }, ...spec.servers.slice(1)] }
        : spec;
      SwaggerUIBundle({
        spec: displaySpec,
        dom_id: '#swagger-ui',
        deepLinking: true,
        defaultModelsExpandDepth: 1,
        docExpansion: 'list',
        persistAuthorization: false,
        presets: [SwaggerUIBundle.presets.apis],
        layout: 'BaseLayout',
        tryItOutEnabled: true,
        validatorUrl: null,
      });
      download.disabled = false;
    } catch (_) {
      if (number !== requestNumber) return;
      document.getElementById('swagger-ui').replaceChildren();
      setStatus(labels.loadError, true);
    }
  }

  async function initialize() {
    setStatus(labels.loading);
    try {
      const services = await call('services');
      availableServices = services;
      if (!services.length) {
        setStatus(labels.noServices);
        return;
      }
      for (const item of services) {
        const option = document.createElement('option');
        option.value = item.key;
        option.textContent = `${item.title} (${item.version || '1.0.0'})`;
        picker.append(option);
      }
      await showService(picker.value);
    } catch (_) {
      setStatus(labels.loadError, true);
    }
  }

  picker.addEventListener('change', () => showService(picker.value));
  download.addEventListener('click', () => {
    if (!currentSpec) return;
    const blob = new Blob([JSON.stringify(currentSpec, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${currentKey.replace(/[^a-z0-9_-]/gi, '-')}-openapi.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  initialize();
})();
