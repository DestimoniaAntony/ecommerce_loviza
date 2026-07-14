// MAISON - Interactive UI Operations

// Toggle Fullscreen Search
function toggleSearch() {
  const overlay = document.getElementById('search-overlay');
  if (overlay) {
    overlay.classList.toggle('active');
    if (overlay.classList.contains('active')) {
      document.body.style.overflow = 'hidden';
      // Auto-focus input
      const input = overlay.querySelector('input');
      if (input) input.focus();
    } else {
      document.body.style.overflow = '';
    }
  }
}

// Toggle Cart Drawer
function toggleCart() {
  const overlay = document.getElementById('cart-drawer-overlay');
  if (overlay) {
    overlay.classList.toggle('active');
    if (overlay.classList.contains('active')) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
  }
}

// Toggle Mobile Menu Navigation
function toggleMobileMenu() {
  const overlay = document.getElementById('mobile-nav-overlay');
  const menuIcon = document.getElementById('mobile-menu-toggle-icon');
  if (overlay) {
    overlay.classList.toggle('active');
    if (overlay.classList.contains('active')) {
      document.body.style.overflow = 'hidden';
      if (menuIcon) menuIcon.textContent = 'close';
    } else {
      document.body.style.overflow = '';
      if (menuIcon) menuIcon.textContent = 'menu';
      const main = document.getElementById('mobile-menu-main');
      const shop = document.getElementById('mobile-menu-shop');
      if (main && shop) {
          main.style.display = 'block';
          shop.style.display = 'none';
      }
    }
  }
}

// Keyboard Listeners (Close on Escape)
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const search = document.getElementById('search-overlay');
    if (search && search.classList.contains('active')) {
      toggleSearch();
    }
    const cart = document.getElementById('cart-drawer-overlay');
    if (cart && cart.classList.contains('active')) {
      toggleCart();
    }
    const mobileMenu = document.getElementById('mobile-nav-overlay');
    if (mobileMenu && mobileMenu.classList.contains('active')) {
      toggleMobileMenu();
    }
    closeLightbox();
  }
});

// Lightbox
function openLightbox() {
  const mainImage = document.getElementById('main-image');
  const lightbox = document.getElementById('image-lightbox');
  const lightboxImg = document.getElementById('lightbox-img');
  
  if (mainImage && lightbox && lightboxImg) {
    lightboxImg.src = mainImage.src;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeLightbox() {
  const lightbox = document.getElementById('image-lightbox');
  if (lightbox) {
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Editorial Carousel Initialization (Homepage)
let currentSlideIndex = 0;
let carouselTimer = null;

function initCarousel() {
  const slides = document.querySelectorAll('.hero-carousel-item');
  if (slides.length === 0) return;

  showSlide(0);
  startCarouselTimer();
}

function showSlide(index) {
  const slides = document.querySelectorAll('.hero-carousel-item');
  if (slides.length === 0) return;

  slides.forEach((slide) => slide.classList.remove('active'));
  slides[index].classList.add('active');
  currentSlideIndex = index;

  // Animate progress indicators
  for (let i = 0; i < slides.length; i++) {
    const progress = document.getElementById(`progress-${i}`);
    if (progress) {
      if (i === index) {
        progress.style.transition = 'none';
        progress.style.transform = 'translateX(-100%)';
        setTimeout(() => {
          progress.style.transition = 'transform 6000ms linear';
          progress.style.transform = 'translateX(0%)';
        }, 50);
      } else {
        progress.style.transition = 'none';
        progress.style.transform = 'translateX(-100%)';
      }
    }
  }
}

function nextSlide() {
  const slides = document.querySelectorAll('.hero-carousel-item');
  if (slides.length === 0) return;
  const nextIndex = (currentSlideIndex + 1) % slides.length;
  showSlide(nextIndex);
}

function setSlide(index) {
  clearInterval(carouselTimer);
  showSlide(index);
  startCarouselTimer();
}

function startCarouselTimer() {
  carouselTimer = setInterval(nextSlide, 6000);
}

// Product Details Accordion (Product Page)
function toggleAccordion(button) {
  const item = button.closest('.accordion-item');
  if (!item) return;

  const isActive = item.classList.contains('active');

  // Close all details items in the wrapper
  const accordionWrapper = item.closest('.accordion-wrapper');
  if (accordionWrapper) {
    accordionWrapper.querySelectorAll('.accordion-item').forEach((el) => {
      el.classList.remove('active');
    });
  }

  // Toggle clicked item
  if (!isActive) {
    item.classList.add('active');
  }
}

// Product Image Selection (Product Page Gallery)
function initProductGallery() {
  const mainImage = document.getElementById('main-image');
  const thumbs = document.querySelectorAll('.thumb-item');
  
  if (!mainImage || thumbs.length === 0) return;

  thumbs.forEach((thumb) => {
    thumb.addEventListener('click', () => {
      // Deactivate other thumbnails
      thumbs.forEach((t) => t.classList.remove('active'));
      
      // Activate clicked thumbnail
      thumb.classList.add('active');
      
      // Update main image source
      const img = thumb.querySelector('img');
      if (img) {
        mainImage.style.opacity = '0.4';
        mainImage.src = img.src;
        mainImage.alt = img.alt;
        setTimeout(() => {
          mainImage.style.opacity = '1';
        }, 150);
      }
    });
  });
}

// Quantity Adjusters (Cart Item Drawers)
function adjustQuantity(button, change) {
  const wrapper = button.closest('.quantity-selector');
  if (!wrapper) return;
  const countEl = wrapper.querySelector('span');
  if (!countEl) return;
  let count = parseInt(countEl.textContent, 10);
  count = Math.max(1, count + change);
  countEl.textContent = count;
}

// Collection Grid Layout Swapper
function setGridCols(cols) {
  const grid = document.querySelector('.collection-product-grid');
  if (!grid) return;
  
  grid.classList.remove('grid-1', 'grid-2', 'grid-3', 'grid-4', 'grid-5');
  grid.classList.add(`grid-${cols}`);
  
  document.querySelectorAll('.grid-toggle-btn').forEach(btn => {
    if (parseInt(btn.getAttribute('data-cols'), 10) === cols) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

// Collection Sidebar Visibility Toggle
function toggleSidebar() {
  const layout = document.querySelector('.collection-layout');
  if (layout) {
    layout.classList.toggle('sidebar-hidden');
  }
}

// Toggle Product Card Wishlist Status
function toggleWishlist(button) {
  button.classList.toggle('active');
  const icon = button.querySelector('span');
  if (button.classList.contains('active')) {
    icon.textContent = 'favorite';
  } else {
    icon.textContent = 'favorite_border';
  }
}

// Dynamic Search Implementation
function initDynamicSearch() {
  const searchInput = document.getElementById('global-search-input');
  if (!searchInput) return;

  const searchUrl = searchInput.getAttribute('data-search-url');
  const suggestionsList = document.getElementById('search-suggestions-list');
  const productsList = document.getElementById('search-products-list');
  const modalFooter = document.getElementById('search-modal-footer');

  let debounceTimer;

  searchInput.addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    const query = e.target.value.trim();

    if (query.length === 0) {
      // Clear results
      if (suggestionsList) suggestionsList.innerHTML = '';
      if (productsList) productsList.innerHTML = '';
      if (modalFooter) modalFooter.innerHTML = '';
      return;
    }

    debounceTimer = setTimeout(() => {
      fetch(`${searchUrl}?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
          // Update Suggestions
          if (suggestionsList) {
            suggestionsList.innerHTML = '';
            if (data.categories && data.categories.length > 0) {
              data.categories.forEach(cat => {
                const li = document.createElement('li');
                li.innerHTML = `<a href="${cat.url}">${cat.title}</a>`;
                suggestionsList.appendChild(li);
              });
            } else {
              suggestionsList.innerHTML = '<li><span style="color: var(--text-muted);">No categories found.</span></li>';
            }
          }

          // Update Products
          if (productsList) {
            productsList.innerHTML = '';
            if (data.products && data.products.length > 0) {
              data.products.forEach(prod => {
                const compareHtml = prod.compare_at 
                  ? `<span style="text-decoration: line-through; color: var(--text-muted); font-size: 0.8em; margin-left: 0.25rem;">${prod.compare_at}</span>` 
                  : '';
                  
                const html = `
                  <a href="${prod.url}" class="search-product-item">
                    <div class="search-product-img" style="background-image: url('${prod.image_url}');"></div>
                    <div class="search-product-info">
                      <span class="search-product-title">${prod.title}</span>
                      <span class="search-product-price">
                        <span style="color: var(--accent-color);">${prod.price}</span>
                        ${compareHtml}
                      </span>
                    </div>
                  </a>
                `;
                productsList.insertAdjacentHTML('beforeend', html);
              });
            } else {
              productsList.innerHTML = '<span style="color: var(--text-muted);">No products match your search.</span>';
            }
          }

          // Update Footer
          if (modalFooter) {
            modalFooter.innerHTML = `<a href="#">Results for "${query}"</a>`;
          }
        })
        .catch(err => console.error("Search error:", err));
    }, 300); // 300ms debounce
  });
}

// Run initializations on DOM Content Loaded
document.addEventListener('DOMContentLoaded', () => {
  initCarousel();
  initProductGallery();
  initDynamicSearch();

  // Set the first accordion active as default
  const firstAccordion = document.querySelector('.accordion-item');
  if (firstAccordion) {
    firstAccordion.classList.add('active');
  }
});
