<script lang="ts">
	import { getContext } from 'svelte';

	import ImagePreview from '$lib/components/common/ImagePreview.svelte';

	const i18n = getContext('i18n');

	// 京津冀预警目前还没有接入真实数据管道，先把拿到的样例图直接贴上来看效果。
	// 之后接入真实产品时，这里要换成从后端接口拉取的最新一张。
	const DEMO_IMAGE_SRC = '/demo/jjj-sample.png';

	let showFullscreen = false;
</script>

<div class="flex flex-col flex-1 min-h-0 gap-2">
	<div
		class="flex-1 min-h-0 flex flex-col rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden"
	>
		<div class="flex-1 min-h-0 flex items-center justify-center p-3 overflow-auto">
			<button
				class="max-w-full max-h-full cursor-zoom-in"
				on:click={() => (showFullscreen = true)}
			>
				<img
					src={DEMO_IMAGE_SRC}
					alt={$i18n.t('Beijing-Tianjin-Hebei Alerts')}
					class="max-w-full max-h-[80vh] object-contain rounded-lg"
				/>
			</button>
		</div>
	</div>
</div>

<ImagePreview
	bind:show={showFullscreen}
	src={DEMO_IMAGE_SRC}
	alt={$i18n.t('Beijing-Tianjin-Hebei Alerts')}
/>
