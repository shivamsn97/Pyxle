(function () {
	const root = document.documentElement;
	let rafId;

	const animateGlow = () => {
		const hue = (Date.now() / 40) % 360;
		root.style.setProperty('--pyxle-glow', `${hue}deg`);
		rafId = requestAnimationFrame(animateGlow);
	};

	const commandBlocks = document.querySelectorAll('[data-pyxle-command]');
	commandBlocks.forEach((block) => {
		block.addEventListener('click', () => {
			const command = block.getAttribute('data-pyxle-command');
			if (!command) return;
			navigator.clipboard?.writeText(command).catch(() => {});
			block.classList.add('pyxle-command--copied');
			setTimeout(() => block.classList.remove('pyxle-command--copied'), 1200);
		});
	});

	animateGlow();

	window.addEventListener('beforeunload', () => {
		if (rafId) cancelAnimationFrame(rafId);
	});
})();
