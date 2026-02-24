/**
 * Mode Panel Component
 */
function modePanel() {
    return {
        protection: null,

        async init() {
            await this.loadProtection();
        },

        async loadProtection() {
            try {
                const res = await fetch('/api/protection');
                this.protection = await res.json();
            } catch (e) {
                console.error('Failed to load protection:', e);
            }
        },

        async setBase(name) {
            await this._postMode('/api/modes/base', { name });
        },

        async addBase(name) {
            await this._postMode('/api/modes/base/add', { name });
        },

        async removeBase(name) {
            await this._postMode('/api/modes/base/remove', { name });
        },

        async pushOverride(name) {
            await this._postMode('/api/modes/override/push', { name });
        },

        async popOverride(name) {
            await this._postMode('/api/modes/override/pop', { name });
        },

        async _postMode(url, body) {
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) {
                    const err = await res.json();
                    alert(err.detail || 'Operation failed');
                    return;
                }
                // Refresh mode state
                const modeRes = await fetch('/api/modes');
                Alpine.store('app').modeState = await modeRes.json();
                await this.loadProtection();
            } catch (e) {
                console.error('Mode operation failed:', e);
            }
        },
    };
}
