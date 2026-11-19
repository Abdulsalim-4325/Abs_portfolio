/* ==========================================================================
   ABSCODE PORTFOLIO — FULL-STACK INTERACTIVITY, POPUPS & 3D CAROUSEL
   ========================================================================== */

const isLocalDev = ['localhost', '127.0.0.1'].includes(window.location.hostname) && window.location.port !== '8000' && window.location.port !== '';
const API_BASE_URL = isLocalDev
  ? `http://${window.location.hostname}:8000/api/v1`
  : `${window.location.origin}/api/v1`;

// Default universal Instagram DM message (includes Name, Purpose & Offer/Connect intent)
const DEFAULT_INSTA_DM_MESSAGE =
  'Hello Abdul Salim! Name: [My Name / Company] | Purpose: [Work / Offer / Collaboration]. I explored your ABSCODE portfolio and would love to connect with you regarding an exciting opportunity!';

document.addEventListener('DOMContentLoaded', () => {

  /* --------------------------------------------------------------------------
     0. ANALYTICS EVENT BEACON (Lightweight Background Tracking)
     -------------------------------------------------------------------------- */
  function trackBeacon(eventType, eventData) {
    try {
      const payload = JSON.stringify({
        event_type: eventType,
        event_data: eventData || null,
        referrer: document.referrer || null,
      });
      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' });
        navigator.sendBeacon(`${API_BASE_URL}/analytics/event`, blob);
      } else {
        fetch(`${API_BASE_URL}/analytics/event`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true,
        }).catch(() => {});
      }
    } catch (_) {}
  }
  // Record initial page visit
  trackBeacon('page_view', window.location.pathname);

  /* --------------------------------------------------------------------------
     1. LIVE UPDATABLE HERO ACHIEVEMENTS & DYNAMIC SITE CONTENT
     -------------------------------------------------------------------------- */
  async function loadPortfolioStats() {
    try {
      const res = await fetch(`${API_BASE_URL}/portfolio-stats`);
      if (!res.ok) return;
      const data = await res.json();
      const pad = (n) => String(n).padStart(2, '0');

      const hackEl = document.getElementById('statHackathons');
      const projEl = document.getElementById('statProjects');
      const paperEl = document.getElementById('statPapers');

      if (hackEl && data.hackathons_count !== undefined) hackEl.textContent = pad(data.hackathons_count);
      if (projEl && data.projects_count !== undefined) projEl.textContent = pad(data.projects_count);
      if (paperEl && data.research_papers_count !== undefined) {
        paperEl.innerHTML = `${pad(data.research_papers_count)}<small>+</small>`;
      }
    } catch (_) {
      // Fallback to default HTML values if backend container is starting up
    }
  }
  loadPortfolioStats();

  async function loadDynamicSiteContent() {
    try {
      const res = await fetch(`${API_BASE_URL}/site-content`);
      if (!res.ok) return;
      const content = await res.json();

      if (content.hero_greeting) {
        const el = document.querySelector('.script-greeting');
        if (el) el.textContent = content.hero_greeting;
      }
      if (content.hero_name) {
        const el = document.querySelector('.hero-name');
        if (el) el.innerHTML = content.hero_name.replace(/\n/g, '<br />');
      }
      if (content.hero_roles) {
        const parsed = content.hero_roles.split(',').map(r => r.trim()).filter(Boolean);
        if (parsed.length) {
          roles.length = 0;
          roles.push(...parsed);
        }
      }
      if (content.hero_description) {
        const el = document.querySelector('.hero-description');
        if (el) el.textContent = content.hero_description;
      }
      if (content.stat_hackathons) {
        const el = document.getElementById('statHackathons');
        if (el) el.textContent = String(content.stat_hackathons).padStart(2, '0');
      }
      if (content.stat_projects) {
        const el = document.getElementById('statProjects');
        if (el) el.textContent = String(content.stat_projects).padStart(2, '0');
      }
      if (content.stat_papers) {
        const el = document.getElementById('statPapers');
        if (el) el.innerHTML = `${String(content.stat_papers).padStart(2, '0')}<small>+</small>`;
      }
      if (content.resume_url && !content.resume_url.includes('github.com')) {
        const navResume = document.getElementById('resumeNavBtn');
        const sheetResume = document.getElementById('sheetResumeOption');
        if (navResume) navResume.href = content.resume_url;
        if (sheetResume) sheetResume.href = content.resume_url;
      }
      if (content.quote_body) {
        const el = document.querySelector('.quote-body');
        if (el) el.textContent = content.quote_body;
      }
      if (content.quote_author) {
        const el = document.querySelector('.quote-signature');
        if (el) el.textContent = content.quote_author;
      }
      if (content.contact_whatsapp) {
        const el = document.querySelector('.whatsapp-option');
        if (el) el.href = content.contact_whatsapp;
      }
    } catch (_) {}
  }
  loadDynamicSiteContent();

  /* --------------------------------------------------------------------------
     2. SLIDE-UP "CONTACT" BOTTOM SHEET POPUP & UNIVERSAL INSTA DM HANDLER
     -------------------------------------------------------------------------- */
  const contactSheetBackdrop = document.getElementById('contactSheetBackdrop');
  const sheetInstaOption = document.getElementById('sheetInstaOption');
  const instaToast = document.getElementById('instaToast');
  const instaTriggers = document.querySelectorAll('.insta-contact-trigger');

  function openContactSheet() {
    if (!contactSheetBackdrop) return;
    contactSheetBackdrop.classList.add('active');
    contactSheetBackdrop.setAttribute('aria-hidden', 'false');
  }

  function closeContactSheet() {
    if (!contactSheetBackdrop) return;
    contactSheetBackdrop.classList.remove('active');
    contactSheetBackdrop.setAttribute('aria-hidden', 'true');
  }

  function copyInstaPrefill() {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(DEFAULT_INSTA_DM_MESSAGE).catch(() => {});
    }
    if (instaToast) {
      instaToast.classList.add('show');
      setTimeout(() => instaToast.classList.remove('show'), 4500);
    }
    closeContactSheet();
  }

  if (sheetInstaOption) sheetInstaOption.addEventListener('click', copyInstaPrefill);
  instaTriggers.forEach((el) => el.addEventListener('click', copyInstaPrefill));

  /* --------------------------------------------------------------------------
     3. GITHUB REPOSITORIES MODAL POPUP
     -------------------------------------------------------------------------- */
  const githubModalBackdrop = document.getElementById('githubModalBackdrop');
  let isUserInteracting = false;

  function openGithubModal() {
    if (!githubModalBackdrop) return;
    githubModalBackdrop.classList.add('active');
    githubModalBackdrop.setAttribute('aria-hidden', 'false');
    isUserInteracting = true;
  }

  function closeGithubModal() {
    if (!githubModalBackdrop) return;
    githubModalBackdrop.classList.remove('active');
    githubModalBackdrop.setAttribute('aria-hidden', 'true');
    isUserInteracting = false;
  }

  document.addEventListener('click', (e) => {
    if (e.target.closest('.open-contact-sheet-btn')) {
      e.preventDefault();
      openContactSheet();
    } else if (e.target.closest('#closeContactSheetBtn') || e.target === contactSheetBackdrop) {
      closeContactSheet();
    } else if (e.target.closest('#openGithubModalBtn')) {
      e.preventDefault();
      openGithubModal();
    } else if (e.target.closest('#closeGithubModalBtn') || e.target === githubModalBackdrop) {
      closeGithubModal();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeGithubModal();
      closeContactSheet();
    }
  });

  /* --------------------------------------------------------------------------
     4. JOB ROLES TYPEWRITER & TRANSITION EFFECT
     -------------------------------------------------------------------------- */
  const roles = [
    'BACKEND SYSTEMS ENGINEER',
    'CYBERSECURITY RESEARCHER',
    'DISTRIBUTED API ARCHITECT',
    'WEB3 & BLOCKCHAIN DEVELOPER',
    'COMPETITIVE JAVA PROGRAMMER'
  ];

  const dynamicRoleEl = document.getElementById('dynamicRole');
  let roleIndex = 0;
  let charIndex = 0;
  let isDeleting = false;

  function animateJobRoles() {
    if (!dynamicRoleEl) return;
    const currentRole = roles[roleIndex];
    charIndex = isDeleting ? charIndex - 1 : charIndex + 1;
    dynamicRoleEl.textContent = currentRole.substring(0, charIndex);

    let speed = isDeleting ? 35 : 70;
    if (!isDeleting && charIndex === currentRole.length) {
      speed = 2000;
      isDeleting = true;
    } else if (isDeleting && charIndex === 0) {
      isDeleting = false;
      roleIndex = (roleIndex + 1) % roles.length;
      speed = 350;
    }
    setTimeout(animateJobRoles, speed);
  }
  animateJobRoles();

  /* --------------------------------------------------------------------------
     5. 3D CIRCULAR PROJECT CAROUSEL (Dynamic FastAPI Loading + HTML Fallback)
     -------------------------------------------------------------------------- */
  const carouselRing = document.getElementById('carouselRing');
  const carouselStage = document.getElementById('carouselStage');
  const prevBtn = document.getElementById('prevProjBtn');
  const nextBtn = document.getElementById('nextProjBtn');
  const dotsContainer = document.getElementById('carouselDots');

  let cards = Array.from(document.querySelectorAll('.project-card-3d'));
  let totalCards = cards.length;
  let theta = totalCards > 0 ? 360 / totalCards : 0;
  let currentIndex = 0;
  let currentAngle = 0;

  const AUTO_ROTATE_INTERVAL_MS = 3200;
  let autoRotateTimer = null;

  function getRadius() {
    const baseRadius = window.innerWidth <= 768 ? 300 : (window.innerWidth <= 1120 ? 440 : 540);
    return Math.max(baseRadius, Math.round(totalCards * (window.innerWidth <= 768 ? 50 : 88)));
  }

  function positionCards3D() {
    if (totalCards === 0) return;
    const radius = getRadius();
    cards.forEach((card, index) => {
      card.style.transform = `rotateY(${theta * index}deg) translateZ(${radius}px)`;
    });
    updateCarousel3D();
  }

  function updateCarousel3D() {
    if (!carouselRing || totalCards === 0) return;
    carouselRing.style.transition = 'transform 0.95s cubic-bezier(0.19, 1, 0.22, 1)';
    carouselRing.style.transform = `rotateY(${currentAngle}deg)`;

    const normalizedIdx = ((currentIndex % totalCards) + totalCards) % totalCards;
    cards.forEach((c, idx) => {
      const isFront = idx === normalizedIdx;
      c.classList.toggle('active-card', isFront);
      const links = c.querySelectorAll('a');
      links.forEach((a) => {
        a.tabIndex = isFront ? 0 : -1;
        a.setAttribute('aria-disabled', String(!isFront));
      });
    });

    const dotButtons = Array.from(document.querySelectorAll('.dot-btn'));
    dotButtons.forEach((d, idx) => d.classList.toggle('active', idx === normalizedIdx));
  }

  function rotateNext() {
    if (totalCards === 0) return;
    currentIndex++;
    currentAngle -= theta;
    updateCarousel3D();
  }

  function rotatePrev() {
    if (totalCards === 0) return;
    currentIndex--;
    currentAngle += theta;
    updateCarousel3D();
  }

  function startAutoRotate() {
    stopAutoRotate();
    autoRotateTimer = setInterval(() => {
      if (!isUserInteracting) rotateNext();
    }, AUTO_ROTATE_INTERVAL_MS);
  }

  function stopAutoRotate() {
    if (autoRotateTimer) {
      clearInterval(autoRotateTimer);
      autoRotateTimer = null;
    }
  }

  function restartAutoRotate() {
    stopAutoRotate();
    startAutoRotate();
  }

  function setupCarouselElements() {
    cards = Array.from(document.querySelectorAll('.project-card-3d'));
    totalCards = cards.length;
    theta = totalCards > 0 ? 360 / totalCards : 0;
    currentIndex = 0;
    currentAngle = 0;

    if (dotsContainer && totalCards > 0) {
      dotsContainer.innerHTML = '';
      cards.forEach((_, idx) => {
        const dot = document.createElement('button');
        dot.className = `dot-btn glow-target ${idx === 0 ? 'active' : ''}`;
        dot.setAttribute('aria-label', `Go to project ${idx + 1}`);
        dot.addEventListener('click', () => {
          const normalizedCurrent = ((currentIndex % totalCards) + totalCards) % totalCards;
          const diff = idx - normalizedCurrent;
          currentIndex += diff;
          currentAngle -= diff * theta;
          updateCarousel3D();
          restartAutoRotate();
        });
        dotsContainer.appendChild(dot);
      });
    }

    positionCards3D();
    if (totalCards > 0) startAutoRotate();
  }

  async function loadDynamicProjects() {
    try {
      const res = await fetch(`${API_BASE_URL}/projects`);
      if (!res.ok) return;
      const projects = await res.json();
      if (Array.isArray(projects) && projects.length > 0 && carouselRing) {
        carouselRing.innerHTML = '';
        projects.forEach((p, idx) => {
          const card = document.createElement('article');
          card.className = 'project-card-3d glow-target';
          card.setAttribute('data-index', idx);
          card.setAttribute('data-title', p.title);

          const liveUrl = p.live_url || p.github_url || '#';
          card.innerHTML = `
            <a href="${liveUrl}" target="_blank" rel="noopener" class="project-img-link" draggable="false">
              <img src="${p.image_url}" alt="${p.title}" draggable="false" onerror="this.src='https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=800&q=80';" />
            </a>
            <div class="project-card-body">
              <h4>${p.title}</h4>
              <p>${p.description}</p>
              <a href="${liveUrl}" target="_blank" rel="noopener" class="view-website-btn glow-target">
                <span>View website</span>
                <i class="bx bx-right-arrow-alt"></i>
              </a>
            </div>
          `;
          carouselRing.appendChild(card);
        });
      }
    } catch (_) {
      // Keep hardcoded fallback HTML cards intact
    } finally {
      setupCarouselElements();
    }
  }
  loadDynamicProjects();

  if (nextBtn) nextBtn.addEventListener('click', () => { rotateNext(); restartAutoRotate(); });
  if (prevBtn) prevBtn.addEventListener('click', () => { rotatePrev(); restartAutoRotate(); });

  let isDragging = false;
  let hasMovedDuringDrag = false;
  let startX = 0;
  let dragStartAngle = 0;

  if (carouselStage && carouselRing) {
    carouselStage.addEventListener('mouseenter', () => { isUserInteracting = true; });
    carouselStage.addEventListener('mouseleave', () => { if (!isDragging) isUserInteracting = false; });

    carouselStage.addEventListener('pointerdown', (e) => {
      if (e.target.closest('.view-website-btn') || e.target.closest('button')) return;
      isDragging = true;
      hasMovedDuringDrag = false;
      isUserInteracting = true;
      startX = e.clientX;
      dragStartAngle = currentAngle;
      carouselRing.style.transition = 'none';
    });

    window.addEventListener('pointermove', (e) => {
      if (!isDragging) return;
      const deltaX = e.clientX - startX;
      if (Math.abs(deltaX) > 8) hasMovedDuringDrag = true;
      const sensitivity = window.innerWidth <= 768 ? 0.35 : 0.22;
      carouselRing.style.transform = `rotateY(${dragStartAngle + deltaX * sensitivity}deg)`;
    });

    const finishDrag = (e) => {
      if (!isDragging) return;
      isDragging = false;
      isUserInteracting = false;
      const deltaX = e.clientX - startX;
      if (deltaX < -35) rotateNext();
      else if (deltaX > 35) rotatePrev();
      else updateCarousel3D();
      restartAutoRotate();
    };

    window.addEventListener('pointerup', finishDrag);
    window.addEventListener('pointercancel', finishDrag);

    carouselStage.addEventListener('click', (e) => {
      const link = e.target.closest('.project-img-link');
      if (link) {
        const parentCard = link.closest('.project-card-3d');
        if (hasMovedDuringDrag || (parentCard && !parentCard.classList.contains('active-card'))) {
          e.preventDefault();
        }
      }
    });

    let wheelCooldown = false;
    carouselStage.addEventListener('wheel', (e) => {
      const horizontalDelta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : (e.shiftKey ? e.deltaY : 0);
      if (Math.abs(horizontalDelta) < 12) return;
      e.preventDefault();
      if (wheelCooldown) return;
      wheelCooldown = true;
      if (horizontalDelta > 0) rotateNext();
      else rotatePrev();
      restartAutoRotate();
      setTimeout(() => { wheelCooldown = false; }, 420);
    }, { passive: false });
  }

  window.addEventListener('resize', positionCards3D);

  /* --------------------------------------------------------------------------
     6. MOBILE NAVBAR TOGGLE & SCROLL SPY
     -------------------------------------------------------------------------- */
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  const navLinks = document.getElementById('navLinks');
  const navItems = document.querySelectorAll('.nav-item');

  if (mobileMenuBtn && navLinks) {
    mobileMenuBtn.addEventListener('click', () => navLinks.classList.toggle('open'));
    navItems.forEach((item) => item.addEventListener('click', () => navLinks.classList.remove('open')));
  }

  const sections = document.querySelectorAll('section[id]');
  window.addEventListener('scroll', () => {
    const scrollY = window.scrollY + 180;
    sections.forEach((sec) => {
      const top = sec.offsetTop;
      const height = sec.offsetHeight;
      const id = sec.getAttribute('id');
      if (scrollY >= top && scrollY < top + height) {
        navItems.forEach((link) => {
          link.classList.toggle('active', link.getAttribute('href') === `#${id}`);
        });
      }
    });
  });

  /* --------------------------------------------------------------------------
     7. VERIFICATION (EMAIL OTP / GOOGLE / GITHUB / INSTAGRAM) & STRICT UNLOCK
     -------------------------------------------------------------------------- */
  const senderNameInput = document.getElementById('senderName') || document.getElementById('nameInput');
  const verifyEmailInput = document.getElementById('verifyEmailInput');
  const verifyAccountLabel = document.getElementById('verifyAccountLabel') || document.querySelector('label[for="verifyEmailInput"]');
  const sendOtpBtn = document.getElementById('sendOtpBtn');
  const confirmOtpBtn = document.getElementById('confirmOtpBtn') || document.getElementById('verifyOtpBtn') || document.querySelector('.verify-otp-btn');
  const otpCodeRow = document.getElementById('otpCodeRow');
  const otpCodeInput = document.getElementById('otpCodeInput');
  const verifyStatusText = document.getElementById('verifyStatusText');
  const verifyBadge = document.getElementById('verifyBadge');
  const verificationTokenInput = document.getElementById('verificationToken');
  const verifiedProviderInput = document.getElementById('verifiedProviderInput');
  const feedbackMsg = document.getElementById('feedbackMsg') || document.getElementById('messageInput');
  const wordCounter = document.getElementById('wordCounter');
  const submitFeedbackBtn = document.getElementById('submitFeedbackBtn');
  const formStatusMsg = document.getElementById('formStatusMsg');
  const oauthPopupLinkRow = document.getElementById('oauthPopupLinkRow');
  const oauthDirectLink = document.getElementById('oauthDirectLink');

  const pillEmailOtp = document.getElementById('pillEmailOtp');
  const googleVerifyBtn = document.getElementById('googleVerifyBtn');
  const githubVerifyBtn = document.getElementById('githubVerifyBtn');
  const instaVerifyBtn = document.getElementById('instaVerifyBtn');

  let currentMethod = 'EMAIL-OTP';
  let isAccountVerified = false;
  let verifiedAccountsMap = {
    email: '',
    insta_id: '',
    google_account: '',
    github_account: ''
  };

  function countWords(str) {
    const trimmed = str.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  }

  function checkUnlockSubmit() {
    const hasName = senderNameInput && senderNameInput.value.trim().length >= 2;
    const hasVerifiedToken = isAccountVerified && verificationTokenInput && verificationTokenInput.value.length > 10;
    const msgText = feedbackMsg ? feedbackMsg.value.trim() : '';
    const hasMin10Chars = msgText.length >= 10;
    const words = countWords(msgText);
    const withinWordLimit = words <= 1000;

    if (submitFeedbackBtn) {
      submitFeedbackBtn.disabled = !(hasName && hasVerifiedToken && hasMin10Chars && withinWordLimit);
    }
  }

  if (senderNameInput) {
    senderNameInput.addEventListener('input', checkUnlockSubmit);
  }

  if (feedbackMsg) {
    feedbackMsg.addEventListener('input', () => {
      const wordsArr = feedbackMsg.value.trim().split(/\s+/).filter(Boolean);
      if (wordsArr.length > 1000) {
        feedbackMsg.value = wordsArr.slice(0, 1000).join(' ');
      }
      const charCount = feedbackMsg.value.trim().length;
      const currentWords = countWords(feedbackMsg.value);
      if (wordCounter) {
        wordCounter.textContent = `${charCount} chars • ${currentWords} / 1000 words`;
        wordCounter.style.color = (charCount < 10 || currentWords >= 1000) ? '#ff4d5a' : '#34d399';
      }
      checkUnlockSubmit();
    });
  }

  if (verifyEmailInput) {
    verifyEmailInput.addEventListener('input', () => {
      if (isAccountVerified) {
        isAccountVerified = false;
        if (verificationTokenInput) verificationTokenInput.value = '';
        if (verifyBadge) {
          verifyBadge.textContent = 'UNVERIFIED';
          verifyBadge.classList.remove('verified');
        }
        checkUnlockSubmit();
      }
    });
  }

  // Method switching controller for all 4 pills
  function switchVerificationMethod(method, autoLaunch = true) {
    currentMethod = method.toUpperCase();

    if (pillEmailOtp) pillEmailOtp.classList.toggle('active-pill', currentMethod === 'EMAIL-OTP');
    if (googleVerifyBtn) googleVerifyBtn.classList.toggle('active-pill', currentMethod === 'GOOGLE');
    if (githubVerifyBtn) githubVerifyBtn.classList.toggle('active-pill', currentMethod === 'GITHUB');
    if (instaVerifyBtn) instaVerifyBtn.classList.toggle('active-pill', currentMethod === 'INSTAGRAM');

    if (otpCodeRow) otpCodeRow.style.display = 'none';

    if (currentMethod === 'EMAIL-OTP') {
      if (verifyAccountLabel) verifyAccountLabel.textContent = 'EMAIL ADDRESS (FOR 6-DIGIT OTP)';
      if (verifyEmailInput) {
        verifyEmailInput.placeholder = 'you@example.com';
        verifyEmailInput.type = 'email';
        verifyEmailInput.readOnly = false;
        if (!isAccountVerified) verifyEmailInput.value = '';
      }
      if (sendOtpBtn) {
        sendOtpBtn.textContent = 'Send OTP';
        sendOtpBtn.style.display = isAccountVerified ? 'none' : 'inline-block';
      }
      if (oauthPopupLinkRow) oauthPopupLinkRow.style.display = 'none';
      if (verifyStatusText && !isAccountVerified) {
        verifyStatusText.style.color = '#a6a6b2';
        verifyStatusText.textContent = 'Enter your email address to receive a 6-digit OTP code.';
      }
    } else if (currentMethod === 'GOOGLE') {
      if (verifyAccountLabel) verifyAccountLabel.textContent = 'GOOGLE ACCOUNT (AUTHENTICATING)';
      if (verifyEmailInput) {
        verifyEmailInput.placeholder = 'Waiting for Google authentication in popup...';
        verifyEmailInput.type = 'text';
        verifyEmailInput.readOnly = true;
        if (!isAccountVerified) verifyEmailInput.value = '';
      }
      if (sendOtpBtn) {
        sendOtpBtn.textContent = 'Open Google Auth';
        sendOtpBtn.style.display = isAccountVerified ? 'none' : 'inline-block';
      }
      if (oauthPopupLinkRow) oauthPopupLinkRow.style.display = 'none';
      if (verifyStatusText && !isAccountVerified) {
        verifyStatusText.style.color = '#ff1e2e';
        verifyStatusText.innerHTML = 'Connecting to Google Authenticator in secure popup... If popup was closed or blocked, click <strong>Google</strong> pill or <strong>Open Google Auth</strong>.';
      }
      if (autoLaunch && !isAccountVerified) {
        window.openOAuthVerifyPopup('google');
      }
    } else if (currentMethod === 'GITHUB') {
      if (verifyAccountLabel) verifyAccountLabel.textContent = 'GITHUB ACCOUNT (AUTHENTICATING)';
      if (verifyEmailInput) {
        verifyEmailInput.placeholder = 'Waiting for GitHub authentication in popup...';
        verifyEmailInput.type = 'text';
        verifyEmailInput.readOnly = true;
        if (!isAccountVerified) verifyEmailInput.value = '';
      }
      if (sendOtpBtn) {
        sendOtpBtn.textContent = 'Open GitHub Auth';
        sendOtpBtn.style.display = isAccountVerified ? 'none' : 'inline-block';
      }
      if (oauthPopupLinkRow) oauthPopupLinkRow.style.display = 'none';
      if (verifyStatusText && !isAccountVerified) {
        verifyStatusText.style.color = '#ff1e2e';
        verifyStatusText.innerHTML = 'Connecting to GitHub Authenticator in secure popup... If popup was closed or blocked, click <strong>GitHub</strong> pill or <strong>Open GitHub Auth</strong>.';
      }
      if (autoLaunch && !isAccountVerified) {
        window.openOAuthVerifyPopup('github');
      }
    } else if (currentMethod === 'INSTAGRAM') {
      if (verifyAccountLabel) verifyAccountLabel.textContent = 'INSTAGRAM ACCOUNT (2-FACTOR AUTH)';
      if (verifyEmailInput) {
        verifyEmailInput.placeholder = 'Waiting for Instagram 2FA in popup...';
        verifyEmailInput.type = 'text';
        verifyEmailInput.readOnly = true;
        if (!isAccountVerified) verifyEmailInput.value = '';
      }
      if (sendOtpBtn) {
        sendOtpBtn.textContent = 'Open Instagram 2FA';
        sendOtpBtn.style.display = isAccountVerified ? 'none' : 'inline-block';
      }
      if (oauthPopupLinkRow) oauthPopupLinkRow.style.display = 'none';
      if (verifyStatusText && !isAccountVerified) {
        verifyStatusText.style.color = '#ff1e2e';
        verifyStatusText.innerHTML = 'Opening Instagram 2-Factor window... Complete verification in popup (or click <strong>Instagram</strong> pill again if popup closed).';
      }
      if (autoLaunch && !isAccountVerified) {
        window.openOAuthVerifyPopup('instagram');
      }
    }
  }

  // Attach click listeners to all 4 pills: Clicking Google, GitHub or Instagram directly opens the authenticator!
  if (pillEmailOtp) {
    pillEmailOtp.addEventListener('click', (e) => {
      e.preventDefault();
      switchVerificationMethod('EMAIL-OTP', false);
    });
  }
  if (googleVerifyBtn) {
    googleVerifyBtn.addEventListener('click', (e) => {
      e.preventDefault();
      switchVerificationMethod('GOOGLE', true);
    });
  }
  if (githubVerifyBtn) {
    githubVerifyBtn.addEventListener('click', (e) => {
      e.preventDefault();
      switchVerificationMethod('GITHUB', true);
    });
  }
  if (instaVerifyBtn) {
    instaVerifyBtn.addEventListener('click', (e) => {
      e.preventDefault();
      switchVerificationMethod('INSTAGRAM', true);
    });
  }

  // Popup Authenticator Launcher
  window.openOAuthVerifyPopup = function(provider) {
    const width = 500;
    const height = 650;
    const left = (window.screen.width - width) / 2;
    const top = (window.screen.height - height) / 2;
    const popupUrl = `${API_BASE_URL}/auth/oauth/${provider}`;

    const popup = window.open(
      popupUrl,
      `Verify_${provider}`,
      `width=${width},height=${height},top=${top},left=${left},scrollbars=yes,resizable=yes`
    );
    if (!popup || popup.closed || typeof popup.closed === 'undefined') {
      if (verifyStatusText) {
        verifyStatusText.style.color = '#ff1e2e';
        verifyStatusText.innerHTML = `Popup was blocked by your browser! Please <a href="${popupUrl}" target="_blank" style="color:#ff1e2e;text-decoration:underline;font-weight:700;">click here to open ${provider.toUpperCase()} verification</a> in a new tab.`;
      }
    }
  };

  if (oauthDirectLink) {
    oauthDirectLink.addEventListener('click', (e) => {
      e.preventDefault();
      const prov = currentMethod === 'GOOGLE' ? 'google' : (currentMethod === 'GITHUB' ? 'github' : 'instagram');
      window.openOAuthVerifyPopup(prov);
    });
  }

  // Listen for verification event from popup authenticators
  window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'OAUTH_VERIFIED') {
      markAccountVerified(event.data.email, event.data.verification_token, event.data.provider);
    }
  });

  function markAccountVerified(identifier, token, provider) {
    isAccountVerified = true;
    if (verificationTokenInput) verificationTokenInput.value = token;
    if (verifiedProviderInput) verifiedProviderInput.value = provider;
    if (verifyEmailInput) {
      verifyEmailInput.value = identifier;
      verifyEmailInput.readOnly = true;
    }

    if (verifyStatusText) {
      verifyStatusText.style.color = '#34d399';
      verifyStatusText.textContent = `✓ Successfully authenticated via ${provider} (${identifier})! Complete your feedback below and submit.`;
    }

    if (verifyBadge) {
      verifyBadge.textContent = `✓ VERIFIED (${provider})`;
      verifyBadge.classList.add('verified');
    }
    if (verifyAccountLabel) {
      verifyAccountLabel.textContent = `VERIFIED ${provider} IDENTITY`;
    }
    if (sendOtpBtn) sendOtpBtn.style.display = 'none';
    if (otpCodeRow) otpCodeRow.style.display = 'none';

    const p = (provider || '').toUpperCase();
    if (p === 'EMAIL-OTP') verifiedAccountsMap.email = identifier;
    else if (p === 'GOOGLE') {
      verifiedAccountsMap.google_account = identifier;
      if (identifier.includes('@')) verifiedAccountsMap.email = identifier;
    } else if (p === 'GITHUB') {
      verifiedAccountsMap.github_account = identifier;
      if (identifier.includes('@')) verifiedAccountsMap.email = identifier;
    } else if (p === 'INSTAGRAM') {
      verifiedAccountsMap.insta_id = identifier;
    }

    checkUnlockSubmit();
  }

  // Trigger OTP Send
  async function triggerSendOtp() {
    const rawVal = verifyEmailInput ? verifyEmailInput.value.trim() : '';
    if (!rawVal) {
      if (verifyStatusText) {
        verifyStatusText.style.color = '#ff4d5a';
        verifyStatusText.textContent = 'Please enter your email or account ID before requesting OTP.';
      }
      if (verifyEmailInput) verifyEmailInput.focus();
      return;
    }

    let deliveryEmail = rawVal;
    if (!deliveryEmail.includes('@')) {
      const promptedEmail = prompt(`Please enter an email address to receive your 6-digit OTP code for "${rawVal}":`);
      if (!promptedEmail || !promptedEmail.includes('@')) {
        if (verifyStatusText) {
          verifyStatusText.style.color = '#ff4d5a';
          verifyStatusText.textContent = 'A valid email is required to deliver the 6-digit verification code.';
        }
        return;
      }
      deliveryEmail = promptedEmail.trim();
    }

    if (sendOtpBtn) sendOtpBtn.disabled = true;
    if (verifyStatusText) {
      verifyStatusText.style.color = '#a6a6b2';
      verifyStatusText.textContent = `Sending 6-digit OTP to ${deliveryEmail}...`;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/auth/send-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: deliveryEmail })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to send OTP code');

      if (verifyEmailInput) {
        verifyEmailInput.dataset.deliveryEmail = deliveryEmail;
        verifyEmailInput.dataset.accountIdentifier = rawVal;
      }

      if (verifyStatusText) {
        verifyStatusText.style.color = '#34d399';
        verifyStatusText.textContent = `✓ 6-digit OTP sent to ${deliveryEmail}! Enter code below:`;
      }
      if (otpCodeRow) otpCodeRow.style.display = 'flex';
      if (otpCodeInput) {
        otpCodeInput.value = '';
        otpCodeInput.focus();
      }
    } catch (err) {
      if (verifyStatusText) {
        verifyStatusText.style.color = '#ff4d5a';
        verifyStatusText.textContent = `✕ ${err.message}`;
      }
    } finally {
      if (sendOtpBtn) sendOtpBtn.disabled = false;
    }
  }

  if (sendOtpBtn) {
    sendOtpBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (currentMethod === 'EMAIL-OTP') {
        triggerSendOtp();
      } else if (currentMethod === 'GOOGLE') {
        window.openOAuthVerifyPopup('google');
      } else if (currentMethod === 'GITHUB') {
        window.openOAuthVerifyPopup('github');
      } else if (currentMethod === 'INSTAGRAM') {
        window.openOAuthVerifyPopup('instagram');
      }
    });
  }

  // Confirm OTP Code
  if (confirmOtpBtn) {
    confirmOtpBtn.addEventListener('click', async (e) => {
      e.preventDefault();

      const deliveryEmail = (verifyEmailInput && verifyEmailInput.dataset.deliveryEmail) || (verifyEmailInput ? verifyEmailInput.value.trim() : '');
      const identifier = (verifyEmailInput && verifyEmailInput.dataset.accountIdentifier) || (verifyEmailInput ? verifyEmailInput.value.trim() : '');
      const otpCode = otpCodeInput ? otpCodeInput.value.trim() : '';

      if (!deliveryEmail || !otpCode) {
        if (verifyStatusText) {
          verifyStatusText.style.color = '#ff4d5a';
          verifyStatusText.textContent = 'Please enter the 6-digit OTP code received in your email.';
        }
        return;
      }

      if (confirmOtpBtn) confirmOtpBtn.disabled = true;
      if (verifyStatusText) {
        verifyStatusText.style.color = '#a6a6b2';
        verifyStatusText.textContent = 'Verifying code...';
      }

      try {
        const res = await fetch(`${API_BASE_URL}/auth/verify-otp`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: deliveryEmail,
            otp_code: otpCode,
            provider: currentMethod,
            identifier: identifier
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Invalid or expired OTP code');

        markAccountVerified(data.email, data.verification_token, data.provider);
      } catch (err) {
        if (verifyStatusText) {
          verifyStatusText.style.color = '#ff4d5a';
          verifyStatusText.textContent = `✕ ${err.message}`;
        }
      } finally {
        if (confirmOtpBtn) confirmOtpBtn.disabled = false;
      }
    });
  }

  // ---------------------------------------------------------
  // INTERACTIVE STAR RATING UI LOGIC (Custom mapped to your HTML)
  // ---------------------------------------------------------
  window.selectedRating = 5; // Default rating
  const starContainer = document.getElementById('starRating');

  if (starContainer) {
      const starBtns = Array.from(starContainer.querySelectorAll('.star-btn'));

      // Function to toggle the 'active' class based on the rating number
      function updateStarsVisual(rating) {
          starBtns.forEach((btn, index) => {
              if (index < rating) {
                  btn.classList.add('active'); 
              } else {
                  btn.classList.remove('active'); 
              }
          });
      }

      // Initialize the default 5-star look
      updateStarsVisual(window.selectedRating);

      // Attach hover and click events to each button
      starBtns.forEach((btn, index) => {
          const val = parseInt(btn.getAttribute('data-val'), 10);

          // Hover effect: preview the rating
          btn.addEventListener('mouseenter', () => {
              updateStarsVisual(val);
          });

          // Click effect: lock in the rating
          btn.addEventListener('click', (e) => {
              e.preventDefault(); // Prevents the button from accidentally submitting the form
              window.selectedRating = val;
              updateStarsVisual(window.selectedRating);
          });
      });

      // Mouse out of the container: revert to the locked rating
      starContainer.addEventListener('mouseleave', () => {
          updateStarsVisual(window.selectedRating);
      });
  }

   
  const activeFeedbackForm = document.getElementById('feedbackForm') || document.querySelector('form');

  if (activeFeedbackForm) {
    activeFeedbackForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const token = verificationTokenInput ? verificationTokenInput.value : '';
      const verifiedId = verifyEmailInput ? verifyEmailInput.value : '';
      const provider = verifiedProviderInput ? verifiedProviderInput.value : '';
      
      if (!token) {
        alert("Security Error: Please verify your identity first.");
        return;
      }

      if (submitFeedbackBtn) submitFeedbackBtn.disabled = true;
      if (formStatusMsg) {
          formStatusMsg.style.color = '#a6a6b2';
          formStatusMsg.textContent = 'Submitting...';
      }

      const rawName = senderNameInput ? senderNameInput.value.trim() : "";
      const msgText = feedbackMsg ? feedbackMsg.value.trim() : "";

      if (rawName.length < 2 || msgText.length < 10) {
          alert("Please make sure your Name is 2+ letters and your Message is at least 10 letters!");
          if (submitFeedbackBtn) submitFeedbackBtn.disabled = false;
          if (formStatusMsg) formStatusMsg.textContent = "";
          return; 
      }

      // Automatically grabs the rating from the new UI block OR hidden radios
      let finalRating = window.selectedRating || 5; 
      const nativeRadio = document.querySelector('input[type="radio"]:checked');
      if (nativeRadio) {
          const radioVal = parseInt(nativeRadio.value, 10);
          if (radioVal >= 1 && radioVal <= 5) finalRating = radioVal;
      }

      try {
        const res = await fetch(`${API_BASE_URL}/feedback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            raw_name_or_company: rawName,
            verified_identifier: verifiedId,
            verification_token: token,
            email: (verifiedId.includes('@') && !verifiedId.startsWith('@')) ? verifiedId : (verifiedAccountsMap.email || null),
            insta_id: (provider === 'INSTAGRAM' || verifiedId.startsWith('@')) ? (verifiedId.startsWith('@') ? verifiedId : `@${verifiedId}`) : null,
            google_account: provider === 'GOOGLE' ? verifiedId : null,
            github_account: provider === 'GITHUB' ? verifiedId : null,
            rating: finalRating,
            message: msgText,
          })
        });

        const data = await res.json();
        if (!res.ok) {
          const msg = Array.isArray(data.detail) ? data.detail[0].msg : data.detail;
          throw new Error(msg || 'Submission failed');
        }

        alert("Feedback submitted successfully!");
        window.location.reload(); 

      } catch (err) {
        if (formStatusMsg) {
            formStatusMsg.style.color = '#ff4d5a';
            formStatusMsg.textContent = `✕ ${err.message}`;
        }
        checkUnlockSubmit();
      }
    });
  }

  /* --------------------------------------------------------------------------
     8. INTERACTION EVENT BEACONS (Project Clicks, Resume, Socials)
     -------------------------------------------------------------------------- */
  document.addEventListener('click', (e) => {
    // Project Click Beacon (3D Carousel Card or Button)
    const projLink = e.target.closest('.view-website-btn') || e.target.closest('.project-img-link');
    if (projLink) {
      const card = projLink.closest('.project-card-3d');
      const title = card ? (card.getAttribute('data-title') || card.querySelector('h4')?.textContent) : 'Project';
      trackBeacon('project_click', (title || 'Project').trim());
    }

    // Resume Download Beacon
    const resumeBtn = e.target.closest('#resumeNavBtn') || e.target.closest('#sheetResumeOption');
    if (resumeBtn) {
      trackBeacon('resume_download', 'Abdul Salim Developer Resume');
    }

    // Social & Direct Channel Clicks
    const socialBtn = e.target.closest('.contact-row-item') || e.target.closest('.sheet-option-card');
    if (socialBtn && !resumeBtn) {
      const label = socialBtn.querySelector('h5, .contact-value')?.textContent || socialBtn.getAttribute('href') || 'Direct Channel';
      trackBeacon('social_click', label.trim());
    }
  });
});