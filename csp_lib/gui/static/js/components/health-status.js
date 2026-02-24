/**
 * Health Status Component
 */
function healthStatus() {
    return {
        healthData: null,

        async init() {
            await this.loadHealth();
        },

        async loadHealth() {
            try {
                const res = await fetch('/api/health');
                this.healthData = await res.json();
            } catch (e) {
                console.error('Failed to load health:', e);
            }
        },
    };
}
