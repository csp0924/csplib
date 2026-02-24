/**
 * Point Monitor Component
 */
function pointMonitor() {
    return {
        filterDevice: '',

        init() {},

        filteredPoints() {
            const rows = [];
            for (const device of Alpine.store('app').devices) {
                const values = device.latest_values || {};
                for (const [point, value] of Object.entries(values)) {
                    if (this.filterDevice && device.device_id !== this.filterDevice) continue;
                    rows.push({
                        device_id: device.device_id,
                        point,
                        value: typeof value === 'number' ? value.toFixed(2) : String(value),
                    });
                }
            }
            return rows;
        },
    };
}
