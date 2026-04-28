<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');

	// import { getGravatarUrl } from '$lib/apis/utils';
	import { canvasPixelTest, generateInitialsImage } from '$lib/utils';

	export let profileImageUrl;
	export let user = null;

	export let imageClassName = 'size-14 md:size-18';

	let profileImageInputElement;

	// Append a cache-busting query string ONLY for the bundled default avatar so that
	// admins replacing /user.png see the new image immediately, without breaking the
	// backend validator which whitelists the bare "/user.png" path.
	$: displayedProfileImageUrl = (() => {
		if (!profileImageUrl) return generateInitialsImage(user?.name);
		if (profileImageUrl === '/user.png' || profileImageUrl.endsWith('/user.png')) {
			const sep = profileImageUrl.includes('?') ? '&' : '?';
			return `${profileImageUrl}${sep}t=${Date.now()}`;
		}
		return profileImageUrl;
	})();
</script>

<input
	id="profile-image-input"
	bind:this={profileImageInputElement}
	type="file"
	hidden
	accept="image/*"
	on:change={(e) => {
		const files = profileImageInputElement.files ?? [];
		let reader = new FileReader();
		reader.onload = (event) => {
			let originalImageUrl = `${event.target.result}`;

			const img = new Image();
			img.src = originalImageUrl;

			img.onload = function () {
				const canvas = document.createElement('canvas');
				const ctx = canvas.getContext('2d');

				// Calculate the aspect ratio of the image
				const aspectRatio = img.width / img.height;

				// Calculate the new width and height to fit within 250x250
				let newWidth, newHeight;
				if (aspectRatio > 1) {
					newWidth = 250 * aspectRatio;
					newHeight = 250;
				} else {
					newWidth = 250;
					newHeight = 250 / aspectRatio;
				}

				// Set the canvas size
				canvas.width = 250;
				canvas.height = 250;

				// Calculate the position to center the image
				const offsetX = (250 - newWidth) / 2;
				const offsetY = (250 - newHeight) / 2;

				// Draw the image on the canvas
				ctx.drawImage(img, offsetX, offsetY, newWidth, newHeight);

				// Get the base64 representation of the compressed image
				const compressedSrc = canvas.toDataURL('image/webp', 0.8);

				// Display the compressed image
				profileImageUrl = compressedSrc;

				profileImageInputElement.files = null;
			};
		};

		if (
			files.length > 0 &&
			['image/gif', 'image/webp', 'image/jpeg', 'image/png'].includes(files[0]['type'])
		) {
			reader.readAsDataURL(files[0]);
		}
	}}
/>

<div class="flex flex-col items-center self-start group">
	<button
		class="relative rounded-2xl overflow-hidden ring-2 ring-gray-200/60 dark:ring-gray-700/40 hover:ring-gray-300 dark:hover:ring-gray-600 transition-all duration-200 shadow-sm"
		type="button"
		on:click={() => {
			profileImageInputElement.click();
		}}
	>
		<img
			src={displayedProfileImageUrl}
			alt="profile"
			class="rounded-2xl {imageClassName} object-cover"
		/>
		<div class="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-all duration-200 flex items-center justify-center">
			<div class="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-5 text-white drop-shadow-md">
					<path d="M1 8a2 2 0 0 1 2-2h.93a2 2 0 0 0 1.664-.89l.812-1.22A2 2 0 0 1 8.07 3h3.86a2 2 0 0 1 1.664.89l.812 1.22A2 2 0 0 0 16.07 6H17a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8Z" />
					<path fill-rule="evenodd" d="M10 14.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM10 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" clip-rule="evenodd" />
				</svg>
			</div>
		</div>
	</button>
	<div class="flex gap-2 mt-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
		<button
			class="text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
			type="button"
			on:click={async () => {
				profileImageUrl = `/user.png`;
			}}>{$i18n.t('Remove')}</button
		>
		<span class="text-gray-300 dark:text-gray-600">|</span>
		<button
			class="text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
			type="button"
			on:click={async () => {
				if (canvasPixelTest()) {
					profileImageUrl = generateInitialsImage(user?.name);
				} else {
					toast.info(
						$i18n.t(
							'Fingerprint spoofing detected: Unable to use initials as avatar. Defaulting to default profile image.'
						),
						{
							duration: 1000 * 10
						}
					);
				}
			}}>{$i18n.t('Initials')}</button
		>
	</div>
</div>
