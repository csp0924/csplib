/**
 * Alarm Panel Component
 */
function alarmPanel() {
    return {
        filterLevel: '',
        filterDevice: '',

        init() {},

        filteredAlarms() {
            let alarms = Alpine.store('app').alarms || [];
            if (this.filterLevel) {
                alarms = alarms.filter(a => a.level === this.filterLevel);
            }
            if (this.filterDevice) {
                alarms = alarms.filter(a => a.device_id === this.filterDevice);
            }
            // Sort: ALARM > WARNING > INFO
            const order = { ALARM: 0, WARNING: 1, INFO: 2 };
            return alarms.sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3));
        },

        async clearAlarm(deviceId, code) {
            try {
                await fetch(`/api/alarms/${deviceId}/${code}/clear`, { method: 'POST' });
                const store = Alpine.store('app');
                store.alarms = store.alarms.filter(
                    a => !(a.device_id === deviceId && a.code === code)
                );
            } catch (e) {
                console.error('Failed to clear alarm:', e);
            }
        },
    };
}
