<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');
</script>

<div class="flex flex-col items-center justify-center flex-1 min-h-0 text-center py-16">
	<div class="text-gray-300 dark:text-gray-600 mb-4">
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="1.5"
			stroke="currentColor"
			class="size-12 mx-auto"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
			/>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z"
			/>
		</svg>
	</div>
	<div class="text-base font-medium text-gray-500 dark:text-gray-400">
		{$i18n.t('Beijing-Tianjin-Hebei Alerts')}
	</div>
	<div class="text-sm text-gray-400 dark:text-gray-500 mt-1">
		{$i18n.t('No data available yet')}
	</div>
</div>
