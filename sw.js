// Service Worker for HostelFlow Kitchen Notifications
const CACHE_NAME = 'hostelflow-kitchen-v1';
const NOTIFICATION_TAG = 'hostelflow-kitchen';

// Install event - cache essential files
self.addEventListener('install', (event) => {
  console.log('🔧 Service Worker: Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('📦 Service Worker: Caching essential files');
        return cache.addAll([
          '/',
          '/static/css/style.css',
          '/static/images/olas-logo.svg'
        ]);
      })
      .then(() => {
        console.log('✅ Service Worker: Installation complete');
        return self.skipWaiting();
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('🚀 Service Worker: Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('🗑️ Service Worker: Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('✅ Service Worker: Activation complete');
      return self.clients.claim();
    })
  );
});

// Push event - handle incoming push notifications
self.addEventListener('push', (event) => {
  console.log('📱 Service Worker: Push notification received');
  
  let notificationData = {
    title: 'HostelFlow Kitchen',
    body: 'New notification received',
    icon: '/static/images/olas-logo.svg',
    badge: '/static/images/olas-logo.svg',
    tag: NOTIFICATION_TAG,
    requireInteraction: true,
    actions: [
      {
        action: 'view',
        title: 'View Details',
        icon: '/static/images/olas-logo.svg'
      },
      {
        action: 'dismiss',
        title: 'Dismiss',
        icon: '/static/images/olas-logo.svg'
      }
    ],
    data: {
      url: '/',
      timestamp: Date.now()
    }
  };

  // Parse push data if available
  if (event.data) {
    try {
      const pushData = event.data.json();
      console.log('📱 Service Worker: Push data:', pushData);
      
      notificationData.title = pushData.title || notificationData.title;
      notificationData.body = pushData.message || pushData.body || notificationData.body;
      notificationData.data = {
        ...notificationData.data,
        ...pushData.data,
        notificationId: pushData.notificationId
      };
      
      // Add sound for mobile devices
      if (pushData.priority === 'high') {
        notificationData.requireInteraction = true;
        notificationData.vibrate = [200, 100, 200];
      }
    } catch (error) {
      console.error('❌ Service Worker: Error parsing push data:', error);
    }
  }

  console.log('📱 Service Worker: Showing notification:', notificationData);
  
  event.waitUntil(
    self.registration.showNotification(notificationData.title, notificationData)
  );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
  console.log('👆 Service Worker: Notification clicked:', event.action);
  
  event.notification.close();
  
  if (event.action === 'dismiss') {
    console.log('👆 Service Worker: Notification dismissed');
    return;
  }
  
  // Default action or 'view' action
  const urlToOpen = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if app is already open
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            console.log('👆 Service Worker: Focusing existing window');
            return client.focus();
          }
        }
        
        // Open new window if app is not open
        if (clients.openWindow) {
          console.log('👆 Service Worker: Opening new window');
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Background sync for offline notifications
self.addEventListener('sync', (event) => {
  console.log('🔄 Service Worker: Background sync triggered');
  
  if (event.tag === 'notification-sync') {
    event.waitUntil(
      // Sync any pending notifications
      fetch('/notifications/api/sync')
        .then(response => response.json())
        .then(data => {
          console.log('🔄 Service Worker: Sync completed:', data);
        })
        .catch(error => {
          console.error('❌ Service Worker: Sync failed:', error);
        })
    );
  }
});

// Message event for communication with main thread
self.addEventListener('message', (event) => {
  console.log('💬 Service Worker: Message received:', event.data);
  
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

console.log('🔧 Service Worker: Script loaded successfully');
