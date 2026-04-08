/**
 * FloorMap — Canvas-based restaurant table renderer.
 * Shared between customer view (read-only) and admin layout builder (editable).
 */
class FloorMap {
    constructor(canvasEl, options = {}) {
        this.canvas = canvasEl;
        this.ctx = canvasEl.getContext('2d');
        this.tables = [];
        this.editable = options.editable || false;
        this.onTableSelect = options.onTableSelect || null;
        this.onLayoutChange = options.onLayoutChange || null;
        this.selectedTableId = null;
        this.availability = {};
        this.dragging = null;
        this.dragOffset = { x: 0, y: 0 };

        this._bindEvents();
        this._resize();
        window.addEventListener('resize', () => this._resize());
    }

    _resize() {
        const parent = this.canvas.parentElement;
        this.canvas.width = parent.clientWidth;
        this.canvas.height = Math.max(400, parent.clientHeight);
        this.render();
    }

    _bindEvents() {
        this.canvas.addEventListener('click', (e) => this._onClick(e));
        if (this.editable) {
            this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
            this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
            this.canvas.addEventListener('mouseup', () => this._onMouseUp());
            this.canvas.addEventListener('touchstart', (e) => this._onTouchStart(e));
            this.canvas.addEventListener('touchmove', (e) => this._onTouchMove(e));
            this.canvas.addEventListener('touchend', () => this._onMouseUp());
        }
    }

    loadLayout(tables) {
        this.tables = (tables || []).map(t => ({ ...t }));
        this.render();
    }

    getLayout() {
        return this.tables.map(t => ({
            id: t.id, label: t.label, shape: t.shape, capacity: t.capacity,
            pos_x: t.pos_x, pos_y: t.pos_y, width: t.width, height: t.height,
        }));
    }

    setAvailability(map) {
        this.availability = map || {};
        this.render();
    }

    selectTable(tableId) {
        this.selectedTableId = tableId;
        this.render();
    }

    addTable(shape, capacity) {
        const id = 'new_' + Date.now();
        this.tables.push({
            id, label: 'T' + (this.tables.length + 1), shape: shape || 'circle',
            capacity: capacity || 4, pos_x: 50 + Math.random() * 200,
            pos_y: 50 + Math.random() * 200, width: 60, height: 60,
        });
        this.render();
        if (this.onLayoutChange) this.onLayoutChange(this.getLayout());
    }

    removeTable(tableId) {
        this.tables = this.tables.filter(t => t.id !== tableId);
        if (this.selectedTableId === tableId) this.selectedTableId = null;
        this.render();
        if (this.onLayoutChange) this.onLayoutChange(this.getLayout());
    }

    render() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        // Background
        ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bo-bg').trim() || '#0F1117';
        ctx.fillRect(0, 0, w, h);

        // Grid dots
        ctx.fillStyle = 'rgba(255,255,255,0.03)';
        for (let x = 0; x < w; x += 20) {
            for (let y = 0; y < h; y += 20) {
                ctx.fillRect(x, y, 1, 1);
            }
        }

        // Tables
        this.tables.forEach(t => {
            const isSelected = t.id === this.selectedTableId;
            const status = this.availability[t.id];
            let fillColor = '#2A2A3A';
            let strokeColor = '#3A3A4E';

            if (status === 'available') { fillColor = 'rgba(16,185,129,0.15)'; strokeColor = '#10B981'; }
            else if (status === 'reserved') { fillColor = 'rgba(239,68,68,0.15)'; strokeColor = '#EF4444'; }
            if (isSelected) { fillColor = 'rgba(255,107,53,0.25)'; strokeColor = '#FF6B35'; }

            ctx.save();
            ctx.fillStyle = fillColor;
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = isSelected ? 3 : 1.5;

            if (t.shape === 'circle') {
                ctx.beginPath();
                ctx.arc(t.pos_x + t.width / 2, t.pos_y + t.height / 2, t.width / 2, 0, Math.PI * 2);
                ctx.fill(); ctx.stroke();
            } else if (t.shape === 'rectangle') {
                const r = 6;
                this._roundRect(ctx, t.pos_x, t.pos_y, t.width, t.height, r);
                ctx.fill(); ctx.stroke();
            } else {
                const r = 6;
                this._roundRect(ctx, t.pos_x, t.pos_y, t.width, t.width, r);
                ctx.fill(); ctx.stroke();
            }

            // Label
            ctx.fillStyle = '#E8E8F0';
            ctx.font = 'bold 11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            const cx = t.pos_x + t.width / 2;
            const cy = t.pos_y + (t.shape === 'square' ? t.width : t.height) / 2;
            ctx.fillText(t.label, cx, cy - 6);

            ctx.font = '9px Inter, sans-serif';
            ctx.fillStyle = '#9CA3B8';
            ctx.fillText(t.capacity + ' 👤', cx, cy + 8);

            ctx.restore();
        });
    }

    _roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    _getTableAt(x, y) {
        for (let i = this.tables.length - 1; i >= 0; i--) {
            const t = this.tables[i];
            const tw = t.shape === 'square' ? t.width : t.width;
            const th = t.shape === 'square' ? t.width : t.height;
            if (x >= t.pos_x && x <= t.pos_x + tw && y >= t.pos_y && y <= t.pos_y + th) return t;
        }
        return null;
    }

    _getCanvasPos(e) {
        const rect = this.canvas.getBoundingClientRect();
        return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }

    _onClick(e) {
        const pos = this._getCanvasPos(e);
        const table = this._getTableAt(pos.x, pos.y);
        if (table) {
            if (this.onTableSelect) this.onTableSelect(table);
            this.selectedTableId = table.id;
            this.render();
        }
    }

    _onMouseDown(e) {
        const pos = this._getCanvasPos(e);
        const table = this._getTableAt(pos.x, pos.y);
        if (table) {
            this.dragging = table;
            this.dragOffset = { x: pos.x - table.pos_x, y: pos.y - table.pos_y };
        }
    }

    _onMouseMove(e) {
        if (!this.dragging) return;
        const pos = this._getCanvasPos(e);
        this.dragging.pos_x = pos.x - this.dragOffset.x;
        this.dragging.pos_y = pos.y - this.dragOffset.y;
        this.render();
    }

    _onMouseUp() {
        if (this.dragging && this.onLayoutChange) this.onLayoutChange(this.getLayout());
        this.dragging = null;
    }

    _onTouchStart(e) {
        e.preventDefault();
        const touch = e.touches[0];
        this._onMouseDown({ clientX: touch.clientX, clientY: touch.clientY });
    }

    _onTouchMove(e) {
        e.preventDefault();
        const touch = e.touches[0];
        this._onMouseMove({ clientX: touch.clientX, clientY: touch.clientY });
    }
}
