(() => {
  const form = document.getElementById('shorten-form');
  const revokeForm = document.getElementById('revoke-form');
  const message = document.getElementById('message');
  const result = document.getElementById('result');
  const shortUrl = document.getElementById('short-url');
  const copyButton = document.getElementById('copy-btn');
  const revokeCurrentButton = document.getElementById('revoke-current-btn');
  const revokeInput = document.getElementById('revoke-input');

  function setMessage(text, type = '') {
    message.textContent = text;
    message.className = `message ${type}`.trim();
  }

  function getShortCodeFromValue(value) {
    const cleaned = value.trim();

    if (!cleaned) {
      return '';
    }

    if (cleaned.includes('://')) {
      try {
        const url = new URL(cleaned);
        return url.pathname.replace(/^\//, '').trim();
      } catch {
        return cleaned.replace(/^.*\//, '').trim();
      }
    }

    return cleaned.replace(/^\//, '');
  }

  function showResult(url) {
    shortUrl.textContent = url;
    shortUrl.href = url;
    result.classList.remove('hidden');
  }

  async function revokeShortCode(shortCode) {
    if (!shortCode) {
      setMessage('Please enter a short code or short URL.', 'error');
      return;
    }

    setMessage('Revoking link...');

    try {
      const response = await fetch('/revoke', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ short_code: shortCode }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Unable to revoke that link right now.');
      }

      setMessage(`Link ${data.short_code} revoked. It will now return 410 Gone.`, 'success');
      if (shortUrl.textContent.endsWith(`/${data.short_code}`)) {
        result.classList.add('hidden');
      }
      revokeInput.value = '';
    } catch (error) {
      setMessage(error.message, 'error');
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
      url: document.getElementById('url-input').value.trim(),
      custom_alias: document.getElementById('alias-input').value.trim(),
    };

    setMessage('Creating your short link...');
    result.classList.add('hidden');

    try {
      const response = await fetch('/shorten', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Unable to shorten that URL right now.');
      }

      showResult(data.short_url);
      setMessage('Link created successfully.', 'success');
      revokeInput.value = data.short_url;
    } catch (error) {
      setMessage(error.message, 'error');
    }
  });

  copyButton.addEventListener('click', async () => {
    if (!shortUrl.textContent) {
      return;
    }

    try {
      await navigator.clipboard.writeText(shortUrl.textContent);
      setMessage('Short link copied to clipboard.', 'success');
    } catch {
      setMessage('Copy failed. You can manually select the link above.', 'error');
    }
  });

  revokeCurrentButton.addEventListener('click', async () => {
    if (!shortUrl.textContent) {
      setMessage('Create a link first, then revoke it.', 'error');
      return;
    }

    await revokeShortCode(getShortCodeFromValue(shortUrl.textContent));
  });

  revokeForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    await revokeShortCode(getShortCodeFromValue(revokeInput.value));
  });
})();
