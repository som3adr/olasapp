// Push Notification Manager for HostelFlow Kitchen Staff
class PushNotificationManager {
    constructor() {
        this.registration = null;
        this.subscription = null;
        this.isSupported = 'serviceWorker' in navigator && 'PushManager' in window;
        this.isKitchenStaff = this.checkIfKitchenStaff();
        this.fallbackMode = false;
        
        console.log('📱 Push Manager: Initialized', {
            isSupported: this.isSupported,
            isKitchenStaff: this.isKitchenStaff
        });
        
        if (this.isKitchenStaff) {
            if (this.isSupported) {
                this.init();
            } else {
                this.initFallbackMode();
            }
        }
    }
    
    initFallbackMode() {
        console.log('📱 Push Manager: Initializing fallback mode (no service worker)');
        this.fallbackMode = true;
        this.updateSubscriptionStatus(false);
        this.showError('Push notifications require a modern browser with Service Worker support. You can still receive in-app notifications.');
    }
    
    checkIfKitchenStaff() {
        // Check if current user is kitchen staff
        const userRole = document.body.getAttribute('data-user-role');
        const isKitchen = userRole === 'Kitchen Staff' || 
                         document.body.classList.contains('kitchen-staff') ||
                         window.location.pathname.includes('kitchen');
        
        console.log('👨‍🍳 Push Manager: Kitchen staff check', {
            userRole: userRole,
            isKitchen: isKitchen
        });
        
        return isKitchen;
    }
    
    async init() {
        try {
            console.log('📱 Push Manager: Initializing...');
            
            // Check if service worker is supported
            if (!('serviceWorker' in navigator)) {
                throw new Error('Service Worker not supported in this browser');
            }
            console.log('✅ Push Manager: Service Worker is supported');
            
            // Check if push manager is supported
            if (!('PushManager' in window)) {
                throw new Error('Push Manager not supported in this browser');
            }
            console.log('✅ Push Manager: Push Manager is supported');
            
            // Register service worker
            console.log('📱 Push Manager: Registering service worker at /sw.js...');
            this.registration = await navigator.serviceWorker.register('/sw.js', {
                scope: '/'
            });
            console.log('✅ Push Manager: Service Worker registered successfully');
            console.log('📋 Push Manager: Registration object:', this.registration);
            
            // Wait for service worker to be ready
            console.log('📱 Push Manager: Waiting for service worker to be ready...');
            this.registration = await navigator.serviceWorker.ready;
            console.log('✅ Push Manager: Service Worker ready');
            console.log('📋 Push Manager: Ready registration object:', this.registration);
            
            // Verify registration has pushManager
            if (!this.registration) {
                throw new Error('Service Worker registration is null');
            }
            
            if (!this.registration.pushManager) {
                throw new Error('Service Worker registration does not have pushManager');
            }
            
            console.log('✅ Push Manager: Push Manager is available');
            
            // Check current subscription
            console.log('📱 Push Manager: Checking current subscription...');
            this.subscription = await this.registration.pushManager.getSubscription();
            console.log('📱 Push Manager: Current subscription:', this.subscription);
            
            // Request permission if not subscribed
            if (!this.subscription) {
                console.log('📱 Push Manager: No subscription found, requesting permission...');
                await this.requestPermission();
            } else {
                console.log('✅ Push Manager: Already subscribed to push notifications');
                this.updateSubscriptionStatus(true);
            }
            
        } catch (error) {
            console.error('❌ Push Manager: Initialization failed:', error);
            console.error('❌ Push Manager: Error stack:', error.stack);
            this.showServiceWorkerError(error);
        }
    }
    
    showServiceWorkerError(error) {
        let errorMessage = '';
        
        if (error.message.includes('Service Worker not supported')) {
            errorMessage = 'Your browser does not support Service Workers. Please use Chrome, Firefox, or Edge.';
        } else if (error.message.includes('pushManager not available')) {
            errorMessage = 'Service Worker registration failed. Please refresh the page and try again.';
        } else if (error.message.includes('Failed to register')) {
            errorMessage = 'Cannot register Service Worker. Make sure you are accessing the site via HTTPS or localhost.';
        } else {
            errorMessage = `Service Worker error: ${error.message}`;
        }
        
        this.showError(errorMessage);
        console.error('📱 Push Manager: Service Worker Error Details:', error);
    }
    
    async retryServiceWorkerRegistration() {
        try {
            console.log('📱 Push Manager: Retrying service worker registration...');
            
            // Unregister existing service workers
            const registrations = await navigator.serviceWorker.getRegistrations();
            for (let registration of registrations) {
                await registration.unregister();
                console.log('📱 Push Manager: Unregistered old service worker');
            }
            
            // Clear caches
            const cacheNames = await caches.keys();
            for (let cacheName of cacheNames) {
                await caches.delete(cacheName);
                console.log('📱 Push Manager: Cleared cache:', cacheName);
            }
            
            // Wait a moment
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            // Reinitialize
            await this.init();
            
        } catch (error) {
            console.error('❌ Push Manager: Retry failed:', error);
            this.showError('Failed to retry service worker registration: ' + error.message);
        }
    }
    
    async requestPermission() {
        try {
            console.log('📱 Push Manager: Requesting notification permission...');
            
            // Check if notifications are supported
            if (!('Notification' in window)) {
                this.showError('This browser does not support notifications. Please use Chrome, Firefox, or Edge.');
                return;
            }
            
            // Check current permission status
            let permission = Notification.permission;
            console.log('📱 Push Manager: Current permission:', permission);
            
            // If permission is not granted, request it
            if (permission === 'default') {
                permission = await Notification.requestPermission();
                console.log('📱 Push Manager: Permission result:', permission);
            }
            
            if (permission === 'granted') {
                await this.subscribeToPush();
            } else if (permission === 'denied') {
                this.showPermissionDeniedHelp();
            } else {
                this.showError('Notification permission not granted. Please enable notifications in your browser settings.');
            }
            
        } catch (error) {
            console.error('❌ Push Manager: Permission request failed:', error);
            this.showError('Failed to request notification permission: ' + error.message);
        }
    }
    
    showPermissionDeniedHelp() {
        const helpMessage = `
            <div class="alert alert-warning">
                <h6><i class="fas fa-exclamation-triangle me-2"></i>Notifications Blocked</h6>
                <p class="mb-2">Your browser has blocked notifications for this site. To enable push notifications:</p>
                <ol class="mb-2">
                    <li><strong>Chrome/Edge:</strong> Click the lock icon (🔒) in the address bar → Allow Notifications</li>
                    <li><strong>Firefox:</strong> Click the shield icon → Permissions → Allow Notifications</li>
                    <li><strong>Safari:</strong> Safari → Preferences → Websites → Notifications → Allow</li>
                </ol>
                <p class="mb-0"><strong>Then refresh this page and try again.</strong></p>
            </div>
        `;
        
        this.showAlert(helpMessage, 'warning');
        
        // Also show a simple error message
        this.showError('Notifications are blocked. Please enable them in your browser settings and refresh the page.');
    }
    
    async subscribeToPush() {
        try {
            console.log('📱 Push Manager: Subscribing to push notifications...');
            
            // Check if registration is available
            if (!this.registration || !this.registration.pushManager) {
                throw new Error('Service Worker registration not available. Please refresh the page and try again.');
            }
            
            // Get VAPID public key from server
            console.log('📱 Push Manager: Getting VAPID public key...');
            const response = await fetch('/notifications/api/vapid-public-key');
            if (!response.ok) {
                throw new Error('Failed to get VAPID public key from server');
            }
            const { publicKey } = await response.json();
            
            console.log('📱 Push Manager: VAPID public key received');
            
            // Subscribe to push manager
            console.log('📱 Push Manager: Creating push subscription...');
            this.subscription = await this.registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(publicKey)
            });
            
            console.log('✅ Push Manager: Subscribed to push notifications');
            
            // Send subscription to server
            await this.sendSubscriptionToServer();
            
        } catch (error) {
            console.error('❌ Push Manager: Subscription failed:', error);
            this.showError('Failed to subscribe to push notifications: ' + error.message);
        }
    }
    
    async sendSubscriptionToServer() {
        try {
            console.log('📱 Push Manager: Sending subscription to server...');
            
            const response = await fetch('/notifications/api/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: this.subscription,
                    userAgent: navigator.userAgent,
                    timestamp: new Date().toISOString()
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                console.log('✅ Push Manager: Subscription sent to server:', result);
                this.updateSubscriptionStatus(true);
                this.showSuccess('Push notifications enabled! You will receive notifications on your phone.');
            } else {
                throw new Error('Server rejected subscription');
            }
            
        } catch (error) {
            console.error('❌ Push Manager: Failed to send subscription to server:', error);
            this.showError('Failed to register for push notifications: ' + error.message);
        }
    }
    
    async unsubscribe() {
        try {
            console.log('📱 Push Manager: Unsubscribing from push notifications...');
            
            if (this.subscription) {
                await this.subscription.unsubscribe();
                this.subscription = null;
                
                // Notify server
                await fetch('/notifications/api/unsubscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                console.log('✅ Push Manager: Unsubscribed from push notifications');
                this.updateSubscriptionStatus(false);
                this.showSuccess('Push notifications disabled.');
            }
            
        } catch (error) {
            console.error('❌ Push Manager: Unsubscribe failed:', error);
            this.showError('Failed to unsubscribe from push notifications: ' + error.message);
        }
    }
    
    updateSubscriptionStatus(isSubscribed) {
        // Update UI elements
        const statusElement = document.getElementById('push-notification-status');
        const toggleButton = document.getElementById('push-notification-toggle');
        
        if (statusElement) {
            statusElement.textContent = isSubscribed ? 'Enabled' : 'Disabled';
            statusElement.className = isSubscribed ? 'badge bg-success' : 'badge bg-secondary';
        }
        
        if (toggleButton) {
            toggleButton.textContent = isSubscribed ? 'Disable Notifications' : 'Enable Notifications';
            toggleButton.className = isSubscribed ? 'btn btn-warning btn-sm' : 'btn btn-success btn-sm';
        }
    }
    
    showSuccess(message) {
        this.showAlert(message, 'success');
    }
    
    showError(message) {
        this.showAlert(message, 'danger');
    }
    
    showAlert(message, type) {
        // Create or update alert element
        let alertElement = document.getElementById('push-notification-alert');
        if (!alertElement) {
            alertElement = document.createElement('div');
            alertElement.id = 'push-notification-alert';
            alertElement.className = 'alert alert-dismissible fade show';
            alertElement.style.position = 'fixed';
            alertElement.style.top = '20px';
            alertElement.style.right = '20px';
            alertElement.style.zIndex = '9999';
            alertElement.style.maxWidth = '400px';
            document.body.appendChild(alertElement);
        }
        
        alertElement.className = `alert alert-${type} alert-dismissible fade show`;
        alertElement.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (alertElement && alertElement.parentNode) {
                alertElement.remove();
            }
        }, 5000);
    }
    
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
}

// Initialize push notification manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('📱 Push Manager: DOM loaded, initializing...');
    window.pushNotificationManager = new PushNotificationManager();
});

// Export for global access
window.PushNotificationManager = PushNotificationManager;
