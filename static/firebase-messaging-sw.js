importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyCUMP5Huo3PvvFXE8_uU2-xZxduDLBPUvY",
  authDomain: "staff-portal-f9d41.firebaseapp.com",
  projectId: "staff-portal-f9d41",
  storageBucket: "staff-portal-f9d41.firebasestorage.app",
  messagingSenderId: "1033220725304",
  appId: "1:1033220725304:web:6735c3b9de88ddf1bba4cd"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage(function(payload) {
  const title = payload.notification?.title || payload.data?.title || 'Staff Update';
  const body = payload.notification?.body || payload.data?.body || '';

  self.registration.showNotification(title, {
    body: body,
    icon: '/static/icon.png',
    badge: '/static/badge.png',
    data: { url: self.location.origin }
  });
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      if (clientList.length > 0) {
        return clientList[0].focus();
      }
      return clients.openWindow(event.notification.data?.url || '/');
    })
  );
});
