<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getContext, createEventDispatcher } from 'svelte';

	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	const dispatch = createEventDispatcher();

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Tags from '$lib/components/chat/Tags.svelte';
	import Share from '$lib/components/icons/Share.svelte';
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte';
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte';
	import Bookmark from '$lib/components/icons/Bookmark.svelte';
	import BookmarkSlash from '$lib/components/icons/BookmarkSlash.svelte';
	import {
		getChatById,
		getChatPinnedStatusById,
		toggleChatPinnedStatusById
	} from '$lib/apis/chats';
	import { chats, folders, settings, theme, user } from '$lib/stores';
	import { createMessagesList, removeDetails, removeAllDetails } from '$lib/utils';
	import { downloadChatAsPDF } from '$lib/apis/utils';
	import Download from '$lib/components/icons/Download.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import Messages from '$lib/components/chat/Messages.svelte';

	const i18n = getContext('i18n');

	export let shareHandler: Function;
	export let moveChatHandler: Function;

	export let cloneChatHandler: Function;
	export let archiveChatHandler: Function;
	export let renameHandler: Function;
	export let deleteHandler: Function;
	export let onClose: Function;

	export let chatId = '';

	let show = false;
	let pinned = false;

	let chat = null;

	const pinHandler = async () => {
		await toggleChatPinnedStatusById(localStorage.token, chatId);
		dispatch('change');
	};

	const checkPinned = async () => {
		pinned = await getChatPinnedStatusById(localStorage.token, chatId);
	};

	const getCleanMessages = (chat) => {
		const history = chat.chat.history;
		const messages = createMessagesList(history, history.currentId);
		return messages
			.filter((m) => m.role === 'user' || m.role === 'assistant')
			.map((m) => {
				let content = m.content || '';
				content = removeDetails(content, ['reasoning', 'code_interpreter']);
				content = removeAllDetails(content);
				content = content.trim();
				return { role: m.role, content };
			})
			.filter((m) => m.content.length > 0);
	};

	const getRoleName = (role) => (role === 'user' ? '用户' : '智能预报员');

	const getChatAsText = async (chat) => {
		const msgs = getCleanMessages(chat);
		return msgs
			.map((m) => `${getRoleName(m.role)}：\n${m.content}`)
			.join('\n\n');
	};

	const downloadTxt = async () => {
		const chat = await getChatById(localStorage.token, chatId);
		if (!chat) return;

		const chatText = await getChatAsText(chat);
		let blob = new Blob([chatText], { type: 'text/plain' });
		saveAs(blob, `chat-${chat.chat.title}.txt`);
	};

	const downloadWord = async () => {
		const chat = await getChatById(localStorage.token, chatId);
		if (!chat) return;

		const { Document, Packer, Paragraph, TextRun } = await import('docx');
		const msgs = getCleanMessages(chat);
		const paragraphs = [];

		for (const m of msgs) {
			paragraphs.push(
				new Paragraph({
					children: [
						new TextRun({
							text: m.role === 'user' ? '用户：' : '智能预报员：',
							bold: true,
							size: 24
						})
					],
					spacing: { before: 240 }
				})
			);
			for (const line of m.content.split('\n')) {
				paragraphs.push(
					new Paragraph({
						children: [new TextRun({ text: line, size: 22 })],
						spacing: { before: 60 }
					})
				);
			}
		}

		const doc = new Document({
			sections: [{ children: paragraphs }]
		});

		const blob = await Packer.toBlob(doc);
		saveAs(blob, `chat-${chat.chat.title}.docx`);
	};

	const downloadPdf = async () => {
		chat = await getChatById(localStorage.token, chatId);
		if (!chat) return;

		const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
			import('jspdf'),
			import('html2canvas-pro')
		]);

		const msgs = getCleanMessages(chat);

		const container = document.createElement('div');
		container.style.cssText =
			'position:fixed;left:-9999px;top:0;width:640px;padding:40px;background:#fff;font-family:system-ui,-apple-system,"Microsoft YaHei","PingFang SC",sans-serif;font-size:14px;line-height:1.8;color:#222;';

		for (const m of msgs) {
			const roleEl = document.createElement('p');
			roleEl.style.cssText = 'font-weight:bold;margin:16px 0 4px 0;';
			roleEl.textContent = getRoleName(m.role) + '：';
			container.appendChild(roleEl);

			for (const line of m.content.split('\n')) {
				const p = document.createElement('p');
				p.style.cssText = 'margin:2px 0;white-space:pre-wrap;word-break:break-all;';
				p.textContent = line;
				container.appendChild(p);
			}
		}

		document.body.appendChild(container);

		try {
			const canvas = await html2canvas(container, {
				scale: 2,
				useCORS: true,
				backgroundColor: '#ffffff'
			});

			const imgData = canvas.toDataURL('image/jpeg', 0.95);
			const imgWidth = 170;
			const pageHeight = 257;
			const imgHeight = (canvas.height * imgWidth) / canvas.width;

			const doc = new jsPDF('p', 'mm', 'a4');
			let heightLeft = imgHeight;
			let position = 20;

			doc.addImage(imgData, 'JPEG', 20, position, imgWidth, imgHeight);
			heightLeft -= pageHeight;

			while (heightLeft > 0) {
				position = heightLeft - imgHeight + 20;
				doc.addPage();
				doc.addImage(imgData, 'JPEG', 20, position, imgWidth, imgHeight);
				heightLeft -= pageHeight;
			}

			doc.save(`chat-${chat.chat.title}.pdf`);
		} finally {
			document.body.removeChild(container);
		}
	};

	const downloadJSONExport = async () => {
		const chat = await getChatById(localStorage.token, chatId);
		if (!chat) return;

		const msgs = getCleanMessages(chat);
		const exportData = msgs.map((m) => ({ [getRoleName(m.role)]: m.content }));

		let blob = new Blob([JSON.stringify(exportData, null, 2)], {
			type: 'application/json'
		});
		saveAs(blob, `chat-${chat.chat.title}.json`);
	};

	$: if (show) {
		checkPinned();
	}
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('More')}>
		<slot />
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="select-none w-full max-w-[210px] rounded-2xl px-1 py-1.5 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg transition"
			sideOffset={-2}
			side="bottom"
			align="start"
			transition={flyAndScale}
		>
			{#if $user?.role === 'admin' || ($user.permissions?.chat?.share ?? true)}
				<DropdownMenu.Item
					draggable="false"
					class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
					on:click={() => {
						shareHandler();
					}}
				>
					<Share strokeWidth="1.5" />
					<div class="flex items-center">分享此对话</div>
				</DropdownMenu.Item>
			{/if}

			<DropdownMenu.Sub>
				<DropdownMenu.SubTrigger
					draggable="false"
					class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				>
					<Download strokeWidth="1.5" />
					<div class="flex items-center">导出对话</div>
				</DropdownMenu.SubTrigger>
				<DropdownMenu.SubContent
					class="select-none min-w-[80px] rounded-2xl p-1 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg border border-gray-100 dark:border-gray-800"
					transition={flyAndScale}
					sideOffset={8}
				>
					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
						on:click={() => {
							downloadWord();
						}}
					>
						<div class="flex items-center line-clamp-1">Word</div>
					</DropdownMenu.Item>

					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
						on:click={() => {
							downloadJSONExport();
						}}
					>
						<div class="flex items-center line-clamp-1">Json</div>
					</DropdownMenu.Item>

					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
						on:click={() => {
							downloadPdf();
						}}
					>
						<div class="flex items-center line-clamp-1">PDF</div>
					</DropdownMenu.Item>

					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
						on:click={() => {
							downloadTxt();
						}}
					>
						<div class="flex items-center line-clamp-1">TXT</div>
					</DropdownMenu.Item>
				</DropdownMenu.SubContent>
			</DropdownMenu.Sub>

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				on:click={() => {
					renameHandler();
				}}
			>
				<Pencil strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Rename')}</div>
			</DropdownMenu.Item>

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				on:click={() => {
					pinHandler();
				}}
			>
				{#if pinned}
					<BookmarkSlash strokeWidth="1.5" />
					<div class="flex items-center">取消置顶</div>
				{:else}
					<Bookmark strokeWidth="1.5" />
					<div class="flex items-center">置顶此对话</div>
				{/if}
			</DropdownMenu.Item>

			<!-- 复制功能已禁用
			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				on:click={() => {
					cloneChatHandler();
				}}
			>
				<DocumentDuplicate strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Clone')}</div>
			</DropdownMenu.Item>
			-->

			<!-- Folders 功能已禁用
			{#if chatId && $folders.length > 0}
				<DropdownMenu.Sub>
					<DropdownMenu.SubTrigger
						draggable="false"
						class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
					>
						<Folder />
						<div class="flex items-center">{$i18n.t('Move')}</div>
					</DropdownMenu.SubTrigger>
					<DropdownMenu.SubContent
						class="select-none w-full max-w-[200px] rounded-2xl p-1 z-50 bg-white dark:bg-gray-850 dark:text-white border border-gray-100 dark:border-gray-800 shadow-lg max-h-52 overflow-y-auto scrollbar-hidden"
						transition={flyAndScale}
						sideOffset={8}
					>
						{#each $folders.sort((a, b) => b.updated_at - a.updated_at) as folder}
							<DropdownMenu.Item
								draggable="false"
								class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl overflow-hidden"
								on:click={() => {
									moveChatHandler(chatId, folder.id);
								}}
							>
								<div class="shrink-0">
									<Folder />
								</div>
								<div class="truncate">{folder?.name ?? 'Folder'}</div>
							</DropdownMenu.Item>
						{/each}
					</DropdownMenu.SubContent>
				</DropdownMenu.Sub>
			{/if}
			-->

			<!-- 归档功能已禁用
			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				on:click={() => {
					archiveChatHandler();
				}}
			>
				<ArchiveBox strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Archive')}</div>
			</DropdownMenu.Item>
			-->

			<hr class="border-gray-200 dark:border-gray-700 my-1" />

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-2 text-sm cursor-pointer hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl text-red-500"
				on:click={() => {
					deleteHandler();
				}}
			>
				<GarbageBin strokeWidth="1.5" />
				<div class="flex items-center">删除此对话</div>
			</DropdownMenu.Item>
		</DropdownMenu.Content>
	</div>
</Dropdown>
