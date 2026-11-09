(() => {
  const regions = () => JSON.parse(document.getElementById('ghana-delivery-regions')?.textContent || '{}');
  function updateDelivery() {
    const rates = JSON.parse(document.getElementById('ghana-delivery-rates')?.textContent || '{}');
    const country = document.getElementById('delivery-country')?.value;
    const region = document.getElementById('delivery-region')?.value;
    const stores = [...document.querySelectorAll('.basket-store')];
    const collectionOnly = stores.length && stores.every(store => store.querySelector('.fulfilment-select')?.value === 'collection');
    for (const name of ['street','region','city']) {
      const field = document.getElementById('delivery-'+name); if (field) field.required = !collectionOnly;
    }
    for (const store of stores) {
      const fee = country === 'GH' ? rates[store.dataset.shop]?.[region] ?? store.dataset.defaultFee : store.dataset.defaultFee;
      store.dataset.deliveryFee = fee;
      const select = store.querySelector('.fulfilment-select');
      select.options[0].textContent = `Delivery · ${store.dataset.currency} ${Number(fee).toFixed(2)}`;
      // The basket's total calculator reads the authoritative seller rate table.
      select.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }
  function towns() {
    const list = document.getElementById('delivery-cities');
    if (!list) return;
    list.replaceChildren(...(regions()[document.getElementById('delivery-region')?.value] || []).map(name => {
      const option = document.createElement('option'); option.value = name; return option;
    }));
  }
  function countryChanged() {
    const previous = document.getElementById('delivery-region');
    if (!previous) return;
    const ghana = document.getElementById('delivery-country').value === 'GH';
    if ((previous.tagName === 'SELECT') === ghana) { towns(); return; }
    const input = document.createElement(ghana ? 'select' : 'input');
    for (const attr of previous.attributes) input.setAttribute(attr.name, attr.value);
    input.removeAttribute('type');
    if (ghana) {
      for (const name of ['', ...Object.keys(regions())]) {
        const option = document.createElement('option'); option.value = name;
        option.textContent = name || 'Choose a region'; input.append(option);
      }
    } else { input.type = 'text'; input.maxLength = 100; input.autocomplete = 'shipping address-level1'; }
    previous.replaceWith(input); towns();
  }
  document.addEventListener('change', event => {
    if (event.target.id === 'delivery-country') { countryChanged(); updateDelivery(); }
    if (event.target.id === 'delivery-region') { towns(); updateDelivery(); }
    if (event.target.matches('.fulfilment-select')) {
      const allCollection = [...document.querySelectorAll('.fulfilment-select')].every(select => select.value === 'collection');
      for (const name of ['street','region','city']) {
        const field = document.getElementById('delivery-'+name); if (field) field.required = !allCollection;
      }
    }
  });
  let busy = false;
  document.addEventListener('click', async event => {
    const button = event.target.closest('#use-location');
    if (!button || busy) return;
    const status = document.getElementById('location-status');
    if (!button.dataset.geoUrl) { status.textContent = 'Location lookup is disabled. Please enter your address below.'; return; }
    if (!navigator.geolocation || !window.isSecureContext) { status.textContent = 'Location needs HTTPS and a supported browser. Please enter your address below.'; return; }
    busy = true; button.disabled = true; status.textContent = 'Waiting for your device location…';
    try {
      const position = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, {enableHighAccuracy:true, timeout:15000, maximumAge:0}));
      status.textContent = 'Finding your region and town…';
      const url = new URL(button.dataset.geoUrl);
      url.search = new URLSearchParams({latitude:position.coords.latitude,longitude:position.coords.longitude,localityLanguage:'en'});
      const response = await fetch(url, {signal:AbortSignal.timeout(10000),credentials:'omit',referrerPolicy:'no-referrer'});
      if (!response.ok) throw new Error('lookup');
      const data = await response.json();
      if (!data.countryCode || !['GH','NG','US','GB'].includes(data.countryCode)) {
        status.textContent = 'This location is outside the supported delivery countries. Enter your intended delivery address manually.'; return;
      }
      const country = document.getElementById('delivery-country'); country.value = data.countryCode; countryChanged();
      const region = document.getElementById('delivery-region');
      const normalize = name => (name || '').toLowerCase().replace(/ region$/,'').trim();
      const regionName = data.principalSubdivision || '';
      const match = Object.keys(regions()).find(name => normalize(name) === normalize(regionName));
      region.value = data.countryCode === 'GH' ? match || '' : regionName;
      document.getElementById('delivery-city').value = data.city || data.locality || '';
      const landmark = document.getElementById('delivery-landmark');
      if (!landmark.value && data.locality && data.locality !== data.city) landmark.value = data.locality;
      towns(); updateDelivery();
      status.textContent = `Location suggested (device accuracy about ${Math.round(position.coords.accuracy)} m). Check your region and town, then add your street and contact details.`;
    } catch (error) {
      status.textContent = error.code === 1 ? 'Location permission was declined. You can enter every address field manually.' : 'We could not look up your location. Please enter your address manually or try again.';
    } finally { busy = false; button.disabled = false; }
  });
  document.addEventListener('DOMContentLoaded', () => { towns(); updateDelivery(); });
  document.addEventListener('htmx:after:swap', () => { towns(); updateDelivery(); });
})();
