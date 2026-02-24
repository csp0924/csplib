/**
 * Command Panel Component
 */
function commandPanel() {
    return {
        selectedDevice: '',
        selectedPoint: '',
        writePoints: [],
        writeValue: '',
        lastResult: { message: '', error: false },

        init() {},

        async loadWritePoints() {
            this.writePoints = [];
            this.selectedPoint = '';
            if (!this.selectedDevice) return;
            try {
                const res = await fetch(`/api/devices/${this.selectedDevice}/write-points`);
                this.writePoints = await res.json();
            } catch (e) {
                console.error('Failed to load write points:', e);
            }
        },

        async sendWrite() {
            try {
                let value = this.writeValue;
                const num = Number(value);
                if (!isNaN(num) && value.trim() !== '') value = num;

                const res = await fetch(`/api/devices/${this.selectedDevice}/write`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        point_name: this.selectedPoint,
                        value,
                    }),
                });
                const data = await res.json();
                if (data.status === 'SUCCESS') {
                    this.lastResult = { message: `Written ${this.selectedPoint} = ${value}`, error: false };
                } else {
                    this.lastResult = { message: data.error_message || 'Write failed', error: true };
                }
            } catch (e) {
                this.lastResult = { message: String(e), error: true };
            }
        },

        async triggerExecutor() {
            try {
                await fetch('/api/executor/trigger', { method: 'POST' });
                this.lastResult = { message: 'Executor triggered', error: false };
            } catch (e) {
                this.lastResult = { message: String(e), error: true };
            }
        },
    };
}
